"""Read-only audit of the supplied kernel artifacts; writes evidence beside this file."""
import hashlib
import json
from pathlib import Path
import re
import struct
import zipfile
import zlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
MAGIC = b"\xd0\x0d\xfe\xed"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def parse_dtbs(data):
    """Validate consecutive FDTs independently of the previous agent's parser."""
    result, base = [], 0
    while base < len(data):
        assert data[base:base + 4] == MAGIC, ("FDT magic", base)
        hdr = struct.unpack_from(">10I", data, base)
        _, total, off_struct, off_strings, off_rsv, version, last, cpu, nstrings, nstruct = hdr
        assert total >= 40 and base + total <= len(data)
        assert version == 17 and last <= 17
        assert off_struct % 4 == 0 and off_rsv % 8 == 0
        assert off_struct + nstruct <= total and off_strings + nstrings <= total
        blob = data[base:base + total]
        reserves, pos = [], off_rsv
        while True:
            assert pos + 16 <= total
            addr, size = struct.unpack_from(">QQ", blob, pos)
            pos += 16
            if addr == size == 0:
                break
            reserves.append([addr, size])
        strings = blob[off_strings:off_strings + nstrings]
        nodes, stack, pos = {}, [], off_struct
        end = off_struct + nstruct
        finished = False
        while pos < end:
            token = struct.unpack_from(">I", blob, pos)[0]
            pos += 4
            if token == 1:
                terminator = blob.index(b"\0", pos, end)
                name = blob[pos:terminator].decode("ascii")
                pos = (terminator + 4) & ~3
                stack.append(name)
                path = "/" + "/".join(stack[1:])
                assert path not in nodes, ("duplicate node", path)
                nodes[path] = {}
            elif token == 2:
                assert stack
                stack.pop()
            elif token == 3:
                assert stack and pos + 8 <= end
                size, nameoff = struct.unpack_from(">II", blob, pos)
                pos += 8
                assert nameoff < len(strings) and pos + size <= end
                name = strings[nameoff:strings.index(b"\0", nameoff)].decode("ascii")
                props = nodes["/" + "/".join(stack[1:])]
                assert name not in props, ("duplicate property", name)
                props[name] = blob[pos:pos + size]
                pos = (pos + size + 3) & ~3
            elif token == 4:
                pass
            elif token == 9:
                assert not stack
                finished = True
                break
            else:
                raise ValueError(("FDT token", token, pos - 4))
        assert finished
        result.append({"offset": base, "size": total, "sha256": sha(blob),
                       "reservations": reserves, "boot_cpuid": cpu, "nodes": nodes})
        base += total
    return result


def cells(data):
    assert len(data) % 4 == 0
    return list(struct.unpack(">" + str(len(data) // 4) + "I", data))


def display(data):
    if data is None:
        return None
    if data and data[0] >= 32 and data.endswith(b"\0") and all(x == 0 or 32 <= x < 127 for x in data):
        return data.rstrip(b"\0").decode("ascii")
    return cells(data) if len(data) % 4 == 0 else data.hex()


def dt_summary(tree):
    n = tree["nodes"]
    return {k: v for k, v in tree.items() if k != "nodes"} | {
        "node_count": len(n), "property_count": sum(map(len, n.values())),
        "model": display(n["/"].get("model")),
        "msm_id": display(n["/"].get("qcom,msm-id")),
        "bootargs": display(n.get("/chosen", {}).get("bootargs")),
        "vendor_fstab": {k: display(v) for k, v in n.get("/firmware/android/fstab/vendor", {}).items()},
        "ramoops": {p: {k: display(v) for k, v in props.items()} for p, props in n.items()
                    if props.get("compatible") == b"ramoops\0"},
        "frequency_model_cpus": [p for p, props in n.items() if "freq-energy-model" in props],
    }


def split_kernel(blob):
    dec = zlib.decompressobj(31)
    image = dec.decompress(blob) + dec.flush()
    assert dec.eof
    return image, dec.unused_data


