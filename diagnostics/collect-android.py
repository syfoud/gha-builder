"""Read-only ADB evidence collection for Android build consistency warnings."""
import argparse
import concurrent.futures
import datetime
import gzip
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import zipfile


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adb', default=r'C:\adb\adb.exe' if pathlib.Path(r'C:\adb\adb.exe').exists() else 'adb')
    p.add_argument('--serial')
    p.add_argument('--out', default='android-evidence')
    p.add_argument('--root', action='store_true', help='Also request su authorization for dmesg and pstore reads')
    args = p.parse_args()
    devices = subprocess.run([args.adb, 'devices', '-l'], capture_output=True, timeout=20)
    rows = [line.split() for line in devices.stdout.decode(errors='replace').splitlines()[1:] if line.strip()]
    available = [row[0] for row in rows if len(row) > 1 and row[1] == 'device' and not row[0].startswith('emulator-')]
    if args.serial:
        if args.serial not in available:
            raise SystemExit('Requested device is not connected and authorized: ' + args.serial)
        serial = args.serial
    elif len(available) == 1:
        serial = available[0]
    else:
        raise SystemExit('Connect exactly one authorized physical device, or specify --serial.\n' + devices.stdout.decode(errors='replace'))
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    folder = pathlib.Path(args.out).resolve() / ('android-' + stamp)
    folder.mkdir(parents=True)
    records = []

    def run(name, tail, timeout=90):
        command = [args.adb, '-s', serial] + tail
        record = {'name': name, 'command': command}
        try:
            result = subprocess.run(command, capture_output=True, timeout=timeout)
            stdout, stderr = result.stdout, result.stderr
            record['exit_code'] = result.returncode
        except subprocess.TimeoutExpired as exc:
            stdout, stderr = exc.stdout or b'', exc.stderr or b''
            record['timeout_seconds'] = timeout
        (folder / (name + '.stdout')).write_bytes(stdout)
        (folder / (name + '.stderr')).write_bytes(stderr)
        record['stdout_sha256'] = hashlib.sha256(stdout).hexdigest()
        return record

    jobs = [
        ('properties', ['shell', 'getprop']),
        ('kernel', ['shell', 'uname -a; cat /proc/version; cat /proc/cmdline; getenforce; cat /proc/uptime']),
        ('checkvintf', ['shell', 'checkvintf --check-compat']),
        ('logcat-all', ['logcat', '-b', 'all', '-d', '-v', 'threadtime']),
        ('config', ['exec-out', 'cat', '/proc/config.gz']),
        ('vintf-files', ['shell', 'find /system/etc/vintf /vendor/etc/vintf /odm/etc/vintf /product/etc/vintf /system_ext/etc/vintf -type f']),
        ('mounts', ['shell', 'cat /proc/mounts; cat /proc/filesystems']),
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(run, name, tail) for name, tail in jobs]
        records.extend(f.result() for f in futures)
    raw = (folder / 'config.stdout').read_bytes()
    config_error = None
    try:
        (folder / 'kernel.config').write_bytes(gzip.decompress(raw))
    except (OSError, EOFError) as exc:
        config_error = str(exc)
    lines = (folder / 'logcat-all.stdout').read_text(encoding='utf-8', errors='replace').splitlines()
    pattern = re.compile(r'build.?consisten|fingerprint|vintf|compatib|kernel config|internal problem|required.*config|CONFIG_[A-Z0-9_]+', re.I)
    (folder / 'logcat-consistency.txt').write_text('\n'.join(line for line in lines if pattern.search(line)) + '\n', encoding='utf-8')
    for directory in ['system', 'vendor', 'odm', 'product', 'system_ext']:
        records.append(run('pull-' + directory + '-vintf', ['pull', '/' + directory + '/etc/vintf', str(folder / (directory + '-vintf'))]))
    if args.root:
        records.append(run('root-kernel', ['shell', 'su', '-c', 'dmesg; ls -la /sys/fs/pstore; cat /sys/fs/pstore/*'], timeout=45))
        if config_error:
            records.append(run('root-config', ['exec-out', 'su', '-c', 'cat /proc/config.gz'], timeout=45))
            try:
                (folder / 'kernel.config').write_bytes(gzip.decompress((folder / 'root-config.stdout').read_bytes()))
                config_error = None
            except (OSError, EOFError) as exc:
                config_error = str(exc)
    report = {'collected_utc': stamp, 'device_serial': serial, 'read_only': True,
              'root_requested': args.root, 'config_read_error': config_error, 'commands': records}
    (folder / 'collection.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    files = [path for path in folder.rglob('*') if path.is_file()]
    (folder / 'SHA256SUMS').write_text(''.join(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.relative_to(folder).as_posix() + '\n' for path in sorted(files)), encoding='utf-8')
    archive = folder.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in folder.rglob('*'):
            if path.is_file():
                z.write(path, path.relative_to(folder.parent))
    print(json.dumps({'folder': str(folder), 'zip': str(archive), 'checkvintf': next(r for r in records if r['name'] == 'checkvintf'), 'config_read_error': config_error}, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
