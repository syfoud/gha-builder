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
if [ "$VARIANT" = next ]; then
  scripts/config --file out/.config --enable KSU --enable KSU_MANUAL_HOOK \
    --disable KSU_KPROBES_HOOK --disable KSU_SYSCALL_TABLE_HOOK --disable KSU_DEBUG
elif [ "$VARIANT" = control ]; then
  scripts/config --file out/.config --disable KSU
else
  echo "Unknown variant: $VARIANT"; exit 1
fi
scripts/config --file out/.config --set-str LOCALVERSION "-Rikka-2005-$VARIANT"
make "${ARGS[@]}" olddefconfig
cp out/.config ../evidence/final.config
scripts/diffconfig ../evidence/base.config out/.config > ../evidence/config-diff.txt
if [ "$VARIANT" = next ]; then
  grep -qx 'CONFIG_KSU=y' out/.config
  grep -qx 'CONFIG_KSU_MANUAL_HOOK=y' out/.config
else
  grep -qx '# CONFIG_KSU is not set' out/.config
fi
grep -qx '# CONFIG_MODULES is not set' out/.config
grep -qx 'CONFIG_SCHED_CASS=y' out/.config
grep -qx 'CONFIG_LRU_GEN=y' out/.config
clang --version > ../evidence/compiler.txt
if [ "$VARIANT" = next ]; then
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
