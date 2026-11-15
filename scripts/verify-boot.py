"""Exercise the shipped ARM magiskboot with a v0/4096/no-ramdisk boot fixture.

Header/layout matches the supplied boot.img. The fixture contains no ROM data.
This tests repacking, not execution of the kernel or the recovery installer.
"""
from pathlib import Path
import gzip
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
from fdt import split_kernel, parse_dtbs

root = Path(__file__).resolve().parent.parent
payload = Path(sys.argv[1]).read_bytes()
ev = Path(sys.argv[2]).resolve()
image, dtb = split_kernel(payload)
old_dtb = (root / 'dtb/2005-dtb.bin').read_bytes().replace(b'Qualcomm', b'TESTcomm', 1)
assert old_dtb != dtb
parse_dtbs(old_dtb)
old_payload = gzip.compress(image, mtime=0) + old_dtb
header = bytearray(4096)
header[:8] = b'ANDROID!'
fields = [len(old_payload), 32768, 0, 0, 0, 0, 256, 4096, 0, 436207979]
struct.pack_into('<10I', header, 8, *fields)
cmdline = (b'console=ttyMSM0,115200n8 earlycon=msm_geni_serial,0xa90000 '
           b'androidboot.hardware=qcom androidboot.console=ttyMSM0 '
           b'androidboot.usbcontroller=a600000.dwc3 service_locator.enable=1 '
           b'loop.max_part=16 androidboot.init_fatal_reboot_target=recovery '
           b'kpti=off buildvariant=userdebug')
header[64:64 + len(cmdline)] = cmdline
digest = hashlib.sha1(old_payload + struct.pack('<I', len(old_payload)) + b'\0' * 8).digest()
header[576:596] = digest
tool = root / 'ak3/tools/magiskboot'
tool.chmod(0o755)
logs, results = [], {}
with tempfile.TemporaryDirectory() as tmp:
    temp = Path(tmp)
    original = temp / 'boot-before.img'
    with original.open('wb') as f:
        f.write(header)
        f.write(old_payload)
        f.truncate(128 * 1024 * 1024)
    for clean in (False, True):
        work = temp / ('clean' if clean else 'old-core')
        work.mkdir()
        def run(*args):
            r = subprocess.run(['qemu-arm', str(tool), *map(str, args)], cwd=work,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            logs.append(r.stdout)
            (ev / 'boot-roundtrip.log').write_text('\n'.join(logs))
            assert r.returncode == 0, r.stdout
        run('unpack', original)
        extracted = sorted(p.name for p in work.iterdir())
        (work / 'kernel').write_bytes(payload)
        if clean:
            (work / 'kernel_dtb').unlink(missing_ok=True)
        output = temp / ('boot-clean.img' if clean else 'boot-old-core.img')
        run('repack', original, output)
        boot = output.read_bytes()
        new_fields = list(struct.unpack_from('<10I', boot, 8))
        assert new_fields[1:] == fields[1:], (new_fields, fields)
        assert boot[48:576] == header[48:576]
        assert boot[608:4096] == header[608:4096]
        assert len(boot) <= 128 * 1024 * 1024
        actual_image, actual_dt = split_kernel(boot[4096:4096 + new_fields[0]])
        assert actual_image == image
        assert len(parse_dtbs(actual_dt)) >= 1
        results['clean' if clean else 'old_core'] = {
            'unpacked_files': extracted, 'native_dtb_preserved': actual_dt == dtb,
            'dtb_count': len(parse_dtbs(actual_dt)),
            'boot_sha256': hashlib.sha256(boot).hexdigest(),
            'header_fields_preserved': True, 'image_preserved': True,
        }
        (ev / 'boot-roundtrip.json').write_text(json.dumps(results, indent=2))
    assert results['clean']['native_dtb_preserved'], results
(ev / 'boot-roundtrip.log').write_text('\n'.join(logs))
(ev / 'boot-roundtrip.json').write_text(json.dumps(results, indent=2))
print('Boot v0 roundtrip:', json.dumps(results))
