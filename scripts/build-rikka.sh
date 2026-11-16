#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/clang-r510928/bin:$PATH"
export KBUILD_BUILD_USER=rikka-rebuild KBUILD_BUILD_HOST=github-actions
export KBUILD_BUILD_TIMESTAMP='Mon Nov 16 00:00:00 UTC 2026'
export KBUILD_BUILD_VERSION=1
cd kernel
ARGS=(O=out ARCH=arm64 LLVM=1 LLVM_IAS=1 CC=clang
  CLANG_TRIPLE=aarch64-linux-gnu- CROSS_COMPILE=aarch64-linux-gnu-
  CROSS_COMPILE_ARM32=arm-linux-gnueabi- CROSS_COMPILE_COMPAT=arm-linux-gnueabi-)
make "${ARGS[@]}" raphael_defconfig
cp out/.config ../evidence/base.config
scripts/config --file out/.config --enable KALLSYMS --enable IKCONFIG --enable IKCONFIG_PROC \
  --enable PRINTK --enable PRINTK_TIME --enable PSTORE --enable PSTORE_CONSOLE \
  --enable PSTORE_PMSG --enable PSTORE_RAM
# Actual requirements from the connected phone's FCM level 3 matrix.
# Keep truthful IKCONFIG and satisfy the matrix with compiled functionality.
scripts/config --file out/.config --enable AUDIT --enable MODULES --enable MODULE_UNLOAD \
  --enable MODVERSIONS --enable NETFILTER_XT_TARGET_NFLOG --enable NF_CT_NETLINK \
  --enable PPP --enable PPP_BSDCOMP --enable PPP_DEFLATE --enable PPP_MPPE \
  --enable PROFILING --enable PERF_EVENTS --enable SECURITY_PERF_EVENTS_RESTRICT \
  --enable UID_SYS_STATS
if [ "$VARIANT" = next ] || [ "$VARIANT" = next-susfs ]; then
  scripts/config --file out/.config --enable KSU --enable KSU_MANUAL_HOOK \
    --disable KSU_KPROBES_HOOK --disable KSU_SYSCALL_TABLE_HOOK --disable KSU_DEBUG
elif [ "$VARIANT" = control ]; then
  scripts/config --file out/.config --disable KSU
else
  echo "Unknown variant: $VARIANT"; exit 1
fi
if [ "$VARIANT" = next-susfs ]; then
  scripts/config --file out/.config --enable KSU_SUSFS --enable KSU_SUSFS_SUS_MOUNT \
    --enable KSU_SUSFS_SUS_KSTAT --enable KSU_SUSFS_SPOOF_UNAME \
    --enable KSU_SUSFS_ENABLE_LOG --enable KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS \
    --enable KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG --enable KSU_SUSFS_SUS_MAP \
    --disable KSU_SUSFS_SUS_PATH --disable KSU_SUSFS_OPEN_REDIRECT
fi
scripts/config --file out/.config --set-str LOCALVERSION "-Rikka-2005-$VARIANT"
make "${ARGS[@]}" olddefconfig
cp out/.config ../evidence/final.config
scripts/diffconfig ../evidence/base.config out/.config > ../evidence/config-diff.txt
python3 ../scripts/check-vintf-config.py out/.config ../config/device-matrix-level3.xml \
  --report ../evidence/vintf-config-check.json
if [ "$VARIANT" = next ] || [ "$VARIANT" = next-susfs ]; then
  grep -qx 'CONFIG_KSU=y' out/.config
  grep -qx 'CONFIG_KSU_MANUAL_HOOK=y' out/.config
else
  grep -qx '# CONFIG_KSU is not set' out/.config
fi
if [ "$VARIANT" = next-susfs ]; then
  grep -qx 'CONFIG_KSU_SUSFS=y' out/.config
fi
grep -qx 'CONFIG_MODULES=y' out/.config
grep -qx 'CONFIG_SCHED_CASS=y' out/.config
grep -qx 'CONFIG_LRU_GEN=y' out/.config
clang --version > ../evidence/compiler.txt
if [ "$VARIANT" = next ] || [ "$VARIANT" = next-susfs ]; then
  # Upstream Kbuild edits kernel headers and fs/SELinux source while parsing.
  # Complete those edits before launching parallel compiler jobs.
  make -f out/.config -f drivers/staging/kernelsu/kernel/Kbuild \
    -f ../scripts/ksu-preflight.mk ksu-preflight srctree="$PWD" objtree="$PWD/out" \
    src=drivers/staging/kernelsu/kernel obj=out/drivers/staging/kernelsu/kernel CC=clang
fi
git diff --binary > ../evidence/kernel-prebuild.patch
make "${ARGS[@]}" -j"$(nproc)" Image.gz-dtb dtbo.img
git diff --binary > ../evidence/kernel-postbuild.patch
cmp ../evidence/kernel-prebuild.patch ../evidence/kernel-postbuild.patch || {
  echo 'Kernel source changed during compilation; refusing a mixed-source artifact'; exit 1;
}
