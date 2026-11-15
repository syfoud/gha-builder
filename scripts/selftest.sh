#!/usr/bin/env bash
# selftest.sh —— 不需要编译，验证打包/清理链路是否正常
# 用法: bash scripts/selftest.sh [测试用内核镜像]
set -euo pipefail
export PYTHONIOENCODING=utf-8
cd "$(dirname "$0")/.."
ROOT=$PWD
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

fail() { echo "  ✗ $1"; exit 1; }
ok()   { echo "  ✓ $1"; }

echo "[1/4] 语法检查"
bash -n ak3/anykernel.sh && ok "anykernel.sh"
bash -n ak3/tools/ksucleanup.sh && ok "ksucleanup.sh"
bash -n scripts/pack.sh && ok "pack.sh"

echo "[2/4] 清理逻辑单测（假 /data/adb）"
FAKE=$TMP/data/adb
mkdir -p "$FAKE/ksu/backup" "$FAKE/ksu"
echo "old-allowlist" > "$FAKE/ksu/.allowlist"
echo "img"          > "$FAKE/ksu/modules.img"
echo "ksud-bin"     > "$FAKE/ksud"
echo "x"            > "$FAKE/modules_update.img"
ui_print() { echo "      [ui] $*"; }
# shellcheck disable=SC1091
. ak3/tools/ksucleanup.sh
ADBDIR="$FAKE" KSU_TS="TEST" ksu_cleanup_legacy >/dev/null
BAK="$FAKE/ksu-legacy-backup-TEST"
[ -d "$BAK/ksu" ] && ok "旧 ksu 目录已备份到 $BAK/ksu" || fail "ksu 未备份"
[ -f "$BAK/ksud" ] && ok "旧 ksud 已备份" || fail "ksud 未备份"
[ -f "$BAK/modules_update.img" ] && ok "modules_update.img 已清理" || fail "modules_update.img 未清理"
[ ! -e "$FAKE/ksu" ] && [ ! -e "$FAKE/ksud" ] && ok "原位置已清空" || fail "原位置仍有残留"
mkdir -p "$FAKE/modules/demo" && echo "[5/4] 保留检查" >/dev/null
ADBDIR="$FAKE" KSU_TS="TEST2" ksu_cleanup_legacy >/dev/null
[ -d "$FAKE/modules/demo" ] && ok "/data/adb/modules 未被误删" || fail "modules 被误删"
KSU_CLEANUP=0 ADBDIR="$FAKE" ksu_cleanup_legacy >/dev/null && ok "do.ksucleanup=0 时可关闭"
# 属性开关 do.ksucleanup=0 也必须生效（模拟 anykernel.sh 的 $home 环境）
FAKEHOME=$TMP/home; mkdir -p "$FAKEHOME"
printf 'do.ksucleanup=0\n' > "$FAKEHOME/anykernel.sh"
file_getprop() { grep -m1 "^$2=" "$1" | cut -d= -f2-; }
home="$FAKEHOME" ADBDIR="$FAKE" KSU_TS="PROP" ksu_cleanup_legacy >/dev/null
if [ ! -d "$FAKE/ksu-legacy-backup-PROP" ]; then ok "do.ksucleanup=0 属性生效（未清理）"; else fail "do.ksucleanup=0 未生效"; fi
unset home
# 属性=1 时必须清理
FAKEHOME2=$TMP/home2; mkdir -p "$FAKEHOME2"; printf 'do.ksucleanup=1\n' > "$FAKEHOME2/anykernel.sh"
mkdir -p "$FAKE/ksu"; echo x > "$FAKE/ksu/.allowlist"
home="$FAKEHOME2" ADBDIR="$FAKE" KSU_TS="PROP2" ksu_cleanup_legacy >/dev/null
if [ -d "$FAKE/ksu-legacy-backup-PROP2/ksu" ]; then ok "do.ksucleanup=1 属性生效（已清理）"; else fail "do.ksucleanup=1 未生效"; fi
unset home

echo "[3/4] 打包链路（dtb_2005 模式）"
IMG_ARG="${1:-}"
if [ -z "$IMG_ARG" ]; then
  for c in "$ROOT/testdata/Image.gz" /e/COUDA/analyisis_core/KSU-Raphael-MIUICX_Kernel_R6.1/Image.gz; do
    [ -f "$c" ] && IMG_ARG=$c && break
  done
fi
if [ -z "$IMG_ARG" ]; then echo "  ! 没有可用的测试镜像，跳过 3/4（传参指定 Image 即可）"; else
  OUT="$TMP/dist" KERNEL_IMG="$IMG_ARG" DTB_MODE=dtb_2005 TAG=selftest bash scripts/pack.sh >/dev/null
  ZIP=$(ls "$TMP"/dist/*.zip)
  PY="$(command -v python3 || true)"; if [ -z "$PY" ] || ! "$PY" -c "import sys" >/dev/null 2>&1; then PY="$(command -v python || true)"; fi
  "$PY" - "$ZIP" <<'PY'
import sys, zipfile, zlib
z = zipfile.ZipFile(sys.argv[1])
names = z.namelist()
assert z.testzip() is None, "zip 损坏"
assert "Image.gz-dtb" in names, "缺 Image.gz-dtb"
blob = z.read("Image.gz-dtb")
d = zlib.decompressobj(31); out = d.decompress(blob); out += d.flush()
assert d.eof, "内核算不对（gzip 未结束）"
dtb = blob[len(blob)-len(d.unused_data):]
assert dtb[:4] == b"\xd0\x0d\xfe\xed", "追加的 DTB 无效"
ak = z.read("anykernel.sh").decode()
core = z.read("tools/ak3-core.sh").decode()
assert "ksu_cleanup_legacy;" in ak, "anykernel.sh 未调用清理"
assert "do.ksucleanup=1" in ak, "未开启 do.ksucleanup"
assert "magiskboot hexpatch" not in core, "面具 hexpatch 残留"
assert ".backup/.magisk" not in core, "面具数据导入残留"
assert "no_magisk_check=1" in ak and "patch_vbmeta_flag=none" in ak
print("      [OK] zip 结构/内核/DTB/清理调用/无面具补丁 全部通过")
print("      [OK] 内核(raw) %d 字节, DTB %d 字节" % (len(out), len(dtb)))
PY
  ok "dtb_2005 打包通过"
fi

echo "[4/4] dtbo 插桩（FLASH_DTBO=true）"
DTBO_C=""
for c in "$ROOT/testdata/dtbo.img" /e/COUDA/analyisis_core/KSU-Raphael-MIUICX_Kernel_R6.1/dtbo.img; do
  [ -f "$c" ] && DTBO_C=$c && break
done
if [ -n "$DTBO_C" ] && [ -n "$IMG_ARG" ]; then
  OUT="$TMP/dist2" KERNEL_IMG="$IMG_ARG" DTB_MODE=dtb_2005 DTBO="$DTBO_C" FLASH_DTBO=true TAG=dtbo bash scripts/pack.sh >/dev/null
  ZIP2=$(ls "$TMP"/dist2/*.zip)
  "$PY" -c "
import zipfile,sys
z=zipfile.ZipFile(sys.argv[1]); ak=z.read('anykernel.sh').decode()
assert 'dtbo.img' in z.namelist(), 'dtbo 未打包'
assert ak.count('flash_dtbo;')==1, 'flash_dtbo 未插入或重复'
print('      ✓ dtbo 打包 + flash_dtbo 插入 通过')" "$ZIP2"
  ok "dtbo 模式通过"
else
  echo "  ! 没有 dtbo 测试文件，跳过 4/4"
fi

echo "全部自测通过 ✅"