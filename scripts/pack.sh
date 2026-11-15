#!/usr/bin/env bash
# pack.sh —— 编译产物 + (可选)2005 设备树 -> AnyKernel3 刷机包
# 环境变量: KERNEL_IMG / KERNEL_GZDTB / DTB_2005 / DTB_MODE(dtb_2005|tree_dtb) / DTBO / FLASH_DTBO / TAG
set -euo pipefail
export PYTHONIOENCODING=utf-8
cd "$(dirname "$0")/.."
ROOT=$PWD
OUT="${OUT:-$ROOT/dist}"; mkdir -p "$OUT"
MODE="${DTB_MODE:-dtb_2005}"
TAG="${TAG:-$(date +%Y%m%d-%H%M)}"
DTB_2005="${DTB_2005:-$ROOT/dtb/2005-dtb.bin}"
NAME="raphael-2005slim-ksunext-$TAG.zip"

rm -rf "$ROOT/build/ak3"; mkdir -p "$ROOT/build"; cp -r "$ROOT/ak3" "$ROOT/build/ak3"
AK3="$ROOT/build/ak3"

gzip_if_needed() {
  case "$1" in
    *.gz) cp -f "$1" "$2" ;;
    *) gzip -9 -c "$1" > "$2" ;;
  esac
}

# 调试变体：DTB 里带 ramoops（卡米后可抓 pstore 日志）
if [ "${DEBUG_RAMOOPS:-false}" = "true" ]; then
  DTB_2005="$ROOT/dtb/2005-dtb-ramoops.bin"
  echo "使用带 ramoops 的 2005 DTB: $DTB_2005"
fi

case "$MODE" in
  tree_dtb)
    if [ -n "${KERNEL_GZDTB:-}" ] && [ -f "${KERNEL_GZDTB}" ]; then
      cp -f "$KERNEL_GZDTB" "$AK3/Image.gz-dtb"
    else
      gzip_if_needed "${KERNEL_IMG:?tree_dtb 模式需要 KERNEL_IMG 或 KERNEL_GZDTB}" "$ROOT/build/Image.gz"
      cat "$ROOT/build/Image.gz" "$DTB_2005" > "$AK3/Image.gz-dtb"
    fi ;;
  dtb_2005)
    [ -f "$DTB_2005" ] || { echo "缺少 DTB_2005: $DTB_2005"; exit 1; }
    gzip_if_needed "${KERNEL_IMG:?dtb_2005 模式需要 KERNEL_IMG}" "$ROOT/build/Image.gz"
    cat "$ROOT/build/Image.gz" "$DTB_2005" > "$AK3/Image.gz-dtb" ;;
  *) echo "未知 DTB_MODE: $MODE"; exit 1 ;;
esac

if [ "${FLASH_DTBO:-false}" = "true" ] && [ -n "${DTBO:-}" ] && [ -f "${DTBO}" ]; then
  cp -f "$DTBO" "$AK3/dtbo.img"
  awk '1; /^flash_boot;/ {print "flash_dtbo;"}' "$AK3/anykernel.sh" > "$AK3/anykernel.sh.new"
  mv -f "$AK3/anykernel.sh.new" "$AK3/anykernel.sh"
  echo "已启用 dtbo 刷写"
fi

PY="$(command -v python3 || true)"
if [ -z "$PY" ] || ! "$PY" -c "import sys" >/dev/null 2>&1; then PY="$(command -v python || true)"; fi
[ -n "$PY" ] || { echo "需要 python3/python 才能打包"; exit 1; }
"$PY" - "$AK3" "$OUT/$NAME" <<'PY'
import os, sys, zipfile
ak3, out = sys.argv[1], sys.argv[2]
if os.path.exists(out): os.remove(out)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for root, dirs, files in os.walk(ak3):
        for fn in sorted(files):
            full = os.path.join(root, fn)
            arc = os.path.relpath(full, ak3).replace(os.sep, "/")
            zi = zipfile.ZipInfo(arc, date_time=(2024, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.create_system = 3
            mode = 0o755 if (arc.endswith("update-binary") or arc.endswith(".sh")) else 0o644
            zi.external_attr = (0o100000 | mode) << 16
            z.write(full, arc, zipfile.ZIP_DEFLATED)
with zipfile.ZipFile(out) as z:
    assert z.testzip() is None
    print("产物:", out)
    print("大小:", os.path.getsize(out), "字节")
    print("Image.gz-dtb 大小:", [i.file_size for i in z.infolist() if i.filename == "Image.gz-dtb"])
PY