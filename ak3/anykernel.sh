### AnyKernel3 Ramdisk Mod Script
## osm0sis @ xda-developers
## 本包 = 开源重编内核(4.14 raphael) + KernelSU-Next；已剔除 Magisk(面具) 全部修补逻辑

### AnyKernel setup
properties() { '
kernel.string=raphael 2005-slim + KernelSU-Next (built from open source)
do.devicecheck=1
do.modules=0
do.systemless=0
do.cleanup=1
do.cleanuponabort=1
do.ksucleanup=1
device.name1=raphael
device.name2=raphaels
device.name3=raphaelin
supported.versions=
supported.patchlevels=
'; } # end properties

### AnyKernel install
block=/dev/block/bootdevice/by-name/boot;
is_slot_device=0;
ramdisk_compression=auto;
no_block_display=true;
# --- Magisk(面具)补丁已剔除: 不做 magisk 检测/内核字符串改写/设备树 verity-avb 改写/vbmeta 标记修改 ---
no_magisk_check=1;
patch_vbmeta_flag=none;
# --- end ---

. tools/ak3-core.sh;
. tools/ksucleanup.sh;

# boot install
split_boot;
mv $home/rd-new.cpio $home/ramdisk-new.cpio
flash_boot;
## end boot install

# 旧 KernelSU(官方线) 用户态残留清理: 备份后移除, 避免与 KernelSU-Next 冲突
ksu_cleanup_legacy;
## end ksu cleanup

# cache clean
rm -rf /cache/*
rm -rf /data/dalvik-cache
rm -rf /data/resource-cache
rm -rf /data/system/package_cache
## end cache clean
