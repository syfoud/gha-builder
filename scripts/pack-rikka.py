"""Fail-closed native-DTB packer, with embedded config and tuning checks."""
from pathlib import Path
import datetime
import gzip
import hashlib
import json
import re
import sys
import subprocess
import zipfile
import zlib
from fdt import parse_dtbs, split_kernel, display

root = Path(__file__).resolve().parent.parent
kernel = Path(sys.argv[1]).resolve()
variant = sys.argv[2]
assert variant in ('next', 'next-susfs', 'control')
ev = root / 'evidence'
ev.mkdir(exist_ok=True)
payload = (kernel / 'out/arch/arm64/boot/Image.gz-dtb').read_bytes()
image, dt = split_kernel(payload)
assert image == (kernel / 'out/arch/arm64/boot/Image').read_bytes()
trees = parse_dtbs(dt)
assert len(trees) == 1, 'Unexpected multiple native DTBs'
native = trees[0]['nodes']
ref = parse_dtbs((root / 'dtb/2005-dtb.bin').read_bytes())[0]['nodes']
assert native['/']['qcom,msm-id'] == ref['/']['qcom,msm-id']
checked, differences = [], []
keys = {'capacity-dmips-mhz', 'freq-energy-model', 'core-cost', 'cluster-cost',
        'core-costs', 'cluster-costs', 'busy-cost-data', 'idle-cost-data',
        'qcom,cpufreq-table-0', 'qcom,cpufreq-table-4', 'qcom,cpufreq-table-7'}
for path, props in ref.items():
    for key, value in props.items():
        if (key in keys or ('ufs' in path and 'qos' in key)
            or (path == '/reserved-memory/linux,cma' and key == 'size')
            or path == '/firmware/android/fstab/vendor'):
            actual = native.get(path, {}).get(key)
            item = {'path': path, 'property': key, 'original': display(value), 'built': display(actual)}
            checked.append(item)
            if value != actual:
                differences.append(item)
(ev / '2005-dtb-comparison.json').write_text(json.dumps({'checked': checked, 'differences': differences}, indent=2))
assert len(checked) >= 30, 'Insufficient tuning coverage'
assert not differences, f'Native DTB lost original 2005 tuning: {differences}'
subprocess.run([sys.executable, str(root / 'scripts/verify-boot.py'),
                str(kernel / 'out/arch/arm64/boot/Image.gz-dtb'), str(ev)], check=True)

config = (kernel / 'out/.config').read_bytes()
start = image.index(b'IKCFG_ST') + 8
dec = zlib.decompressobj(31)
embedded = dec.decompress(image[start:]) + dec.flush()
assert dec.eof and dec.unused_data.startswith(b'IKCFG_ED')
assert embedded == config, 'Embedded config differs from final .config'
required = [b'CONFIG_SCHED_CASS=y', b'CONFIG_LRU_GEN=y', b'CONFIG_KALLSYMS=y',
            b'CONFIG_PSTORE_RAM=y', b'CONFIG_IKCONFIG=y', b'CONFIG_AUDIT=y',
            b'CONFIG_MODULES=y', b'CONFIG_MODVERSIONS=y']
for line in required:
    assert line in config.splitlines(), line
if variant in ('next', 'next-susfs'):
    release_port = json.loads((ev / 'release-port.json').read_text())
    assert release_port['release_commit'] == '4c706b5938665866ebe16944a481a7b91e3396af'
    assert release_port['uapi_version'] == 5
    for name, expected in release_port['release_uapi_files_unchanged'].items():
        assert hashlib.sha256((kernel / 'drivers/staging/kernelsu' / name).read_bytes()).hexdigest() == expected
    for line in [b'CONFIG_KSU=y', b'CONFIG_KSU_MANUAL_HOOK=y']:
        assert line in config.splitlines()
    syms = (kernel / 'out/System.map').read_text()
    for sym in ['ksu_handle_sys_reboot', 'ksu_handle_execveat', 'ksu_handle_vfs_read',
                'ksu_handle_newfstat_ret', 'ksu_handle_faccessat', 'ksu_handle_stat',
                'ksu_handle_input_handle_event', 'ksu_handle_setresuid']:
        assert re.search(r'\b' + sym + r'$', syms, re.M), sym
else:
    assert b'# CONFIG_KSU is not set' in config.splitlines()
if variant == 'next-susfs':
    for line in [b'CONFIG_KSU_SUSFS=y', b'CONFIG_KSU_SUSFS_SUS_MOUNT=y',
                 b'CONFIG_KSU_SUSFS_SUS_KSTAT=y', b'CONFIG_KSU_SUSFS_SUS_MAP=y',
                 b'# CONFIG_KSU_SUSFS_ENABLE_LOG is not set',
                 b'# CONFIG_KSU_SUSFS_SUS_PATH is not set',
                 b'# CONFIG_KSU_SUSFS_OPEN_REDIRECT is not set']:
        assert line in config.splitlines(), line
    for sym in ['susfs_init', 'susfs_show_version', 'ksu_susfs_reboot',
                'ksu_susfs_after_setuid', 'ksu_susfs_policy_loaded',
                'susfs_add_sus_map', 'susfs_sus_kstat_spoof_generic_fillattr',
                'susfs_get_non_sus_mnt_id_from_mnt', 'susfs_start_sdcard_monitor_fn']:
        assert re.search(r'\b' + sym + r'$', syms, re.M), sym
    assert b'v2.2.0' in image
version = re.search(rb'Linux version [^\0\n]+', image).group().decode()
manifest = {'variant': variant, 'kernel_version': version,
            'build_flavor': 'vintf-repair',
            'susfs_version': 'v2.2.0-NON-GKI' if variant == 'next-susfs' else None,
            'susfs_port_reference': 'Fansirsqi/raphael-kernel@2a723dc65ed70db121194b4b0da8215b3c5615c6' if variant == 'next-susfs' else None,
            'susfs_disabled_features': ['ENABLE_LOG', 'SUS_PATH', 'OPEN_REDIRECT'] if variant == 'next-susfs' else [],
            'kernel_sha': '222b8d42dde3f13973357cae50359fa2aca8239d',
            'ksu_sha': '4c706b5938665866ebe16944a481a7b91e3396af' if variant in ('next', 'next-susfs') else None,
            'ksu_release': 'v3.4.2', 'ksu_uapi': 5,
            'ksu_manual_hook_reference': '8af3d4fec33be32fa5d3f8dae4f380fac45bf2cd',
            'sha256': {name: hashlib.sha256(data).hexdigest() for name, data in
                       [('Image', image), ('native.dtb', dt), ('Image.gz-dtb', payload), ('.config', config)]},
            'tuning_properties_verified': len(checked), 'embedded_config_matches': True,
            'device_tested': False, 'dtbo_flashed': False,
            'pstore_note': 'PSTORE_RAM compiled in; no unverified physical RAM region is reserved.'}
(ev / 'manifest.json').write_text(json.dumps(manifest, indent=2))

ak = (root / 'scripts/anykernel-rikka.sh').read_text().replace('@VARIANT@', variant)
name = f'raphael-rikka-2005-{variant}-vintf-{manifest["kernel_sha"][:8]}-{manifest["ksu_sha"][:8] if manifest["ksu_sha"] else "no-root"}.zip'
out = root / 'dist'
out.mkdir(exist_ok=True)
files = {'Image.gz-dtb': payload, 'anykernel.sh': ak.encode(),
         'build-manifest.json': json.dumps(manifest, indent=2).encode()}
for path in (root / 'ak3').rglob('*'):
    if path.is_file() and path.name != 'anykernel.sh':
        files[path.relative_to(root / 'ak3').as_posix()] = path.read_bytes()
for path in (root / 'diagnostics').glob('*'):
    if path.is_file():
        files['diagnostics/' + path.name] = path.read_bytes()
with zipfile.ZipFile(out / name, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for path, data in sorted(files.items()):
        zi = zipfile.ZipInfo(path, (2026, 11, 16, 0, 0, 0))
        zi.create_system = 3
        executable = path.startswith('tools/') or path.endswith('.sh') or path.endswith('update-binary') or path == 'diagnostics/root-api-probe'
        zi.external_attr = (0o100755 if executable else 0o100644) << 16
        zi.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(zi, data)
with zipfile.ZipFile(out / name) as z:
    assert z.testzip() is None
    assert z.read('Image.gz-dtb') == payload
(out / (name + '.sha256')).write_text(hashlib.sha256((out / name).read_bytes()).hexdigest() + '  ' + name + '\n')
print(json.dumps(manifest, indent=2))
print('Validated package:', out / name)
