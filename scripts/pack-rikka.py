"""Fail-closed native-DTB packer, with embedded config and tuning checks."""
from pathlib import Path
import datetime
import gzip
import hashlib
import json
import re
import sys
import zipfile
import zlib
from fdt import parse_dtbs, split_kernel, display

root = Path(__file__).resolve().parent.parent
kernel = Path(sys.argv[1]).resolve()
variant = sys.argv[2]
assert variant in ('next', 'control')
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

config = (kernel / 'out/.config').read_bytes()
start = image.index(b'IKCFG_ST') + 8
dec = zlib.decompressobj(31)
embedded = dec.decompress(image[start:]) + dec.flush()
assert dec.eof and dec.unused_data.startswith(b'IKCFG_ED')
assert embedded == config, 'Embedded config differs from final .config'
required = [b'CONFIG_SCHED_CASS=y', b'CONFIG_LRU_GEN=y', b'CONFIG_KALLSYMS=y',
            b'CONFIG_PSTORE_RAM=y', b'CONFIG_IKCONFIG=y']
for line in required:
    assert line in config.splitlines(), line
if variant == 'next':
    for line in [b'CONFIG_KSU=y', b'CONFIG_KSU_MANUAL_HOOK=y']:
        assert line in config.splitlines()
    syms = (kernel / 'out/System.map').read_text()
    for sym in ['ksu_handle_sys_reboot', 'ksu_handle_execveat', 'ksu_handle_vfs_read',
                'ksu_handle_newfstat_ret', 'ksu_handle_faccessat', 'ksu_handle_stat',
                'ksu_handle_input_handle_event', 'ksu_handle_setresuid']:
        assert re.search(r'\b' + sym + r'$', syms, re.M), sym
else:
    assert b'# CONFIG_KSU is not set' in config.splitlines()
version = re.search(rb'Linux version [^\0\n]+', image).group().decode()
manifest = {'variant': variant, 'kernel_version': version,
            'kernel_sha': '222b8d42dde3f13973357cae50359fa2aca8239d',
            'ksu_sha': 'e5f5ec998de88b9fc43c62cff8f7ae12d3f4800a' if variant == 'next' else None,
            'sha256': {name: hashlib.sha256(data).hexdigest() for name, data in
                       [('Image', image), ('native.dtb', dt), ('Image.gz-dtb', payload), ('.config', config)]},
            'tuning_properties_verified': len(checked), 'embedded_config_matches': True,
            'device_tested': False, 'dtbo_flashed': False,
            'pstore_note': 'PSTORE_RAM compiled in; no unverified physical RAM region is reserved.'}
(ev / 'manifest.json').write_text(json.dumps(manifest, indent=2))

ak = (root / 'scripts/anykernel-rikka.sh').read_text().replace('@VARIANT@', variant)
name = f'raphael-rikka-2005-{variant}-{manifest["kernel_sha"][:8]}-{manifest["ksu_sha"][:8] if variant == "next" else "no-root"}.zip'
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
        executable = path.startswith('tools/') or path.endswith('.sh') or path.endswith('update-binary')
        zi.external_attr = (0o100755 if executable else 0o100644) << 16
        zi.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(zi, data)
with zipfile.ZipFile(out / name) as z:
    assert z.testzip() is None
    assert z.read('Image.gz-dtb') == payload
(out / (name + '.sha256')).write_text(hashlib.sha256((out / name).read_bytes()).hexdigest() + '  ' + name + '\n')
print(json.dumps(manifest, indent=2))
print('Validated package:', out / name)
