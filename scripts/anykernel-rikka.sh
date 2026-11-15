### AnyKernel3, Rikka 2005 source rebuild
properties() { '
kernel.string=Rikka 2005 source + @VARIANT@ (experimental rebuild)
do.devicecheck=1
do.modules=0
do.systemless=0
do.cleanup=1
do.cleanuponabort=1
device.name1=raphael
device.name2=raphaels
device.name3=raphaelin
supported.versions=
supported.patchlevels=
'; }
block=/dev/block/bootdevice/by-name/boot;
is_slot_device=0;
ramdisk_compression=auto;
no_block_display=true;
no_magisk_check=1;
patch_vbmeta_flag=none;
. tools/ak3-core.sh;
split_boot;

# Preserve the exact pre-flash boot and evidence before writing anything.
# /sdcard must be mounted and decrypted in recovery.
stamp=$(date +%Y%m%d-%H%M%S);
savedir=/sdcard/Rikka-rescue/$stamp-@VARIANT@;
mkdir -p "$savedir" || abort "Cannot create boot backup. Mount/decrypt /data first.";
cp "$bootimg" "$savedir/boot-before.img" || abort "Boot backup failed.";
cmp -s "$bootimg" "$savedir/boot-before.img" || abort "Boot backup verification failed.";
cp "$home/build-manifest.json" "$savedir/" || abort "Cannot save build identity.";
cp /tmp/recovery.log "$savedir/recovery-before.log" 2>/dev/null;
cat /proc/cmdline > "$savedir/recovery-cmdline.txt";
sync;
ui_print "Boot backup: $savedir/boot-before.img";

# A complete Image.gz-dtb already carries this build's DTB. Do not append
# a second kernel_dtb extracted from the previous boot image at repack time.
rm -f "$split_img/kernel_dtb";
flash_boot;
dd if="$block" of="$savedir/boot-after.img" bs=1048576 2>/dev/null || abort "Boot readback failed. Restore boot-before.img.";
newsize=$(wc -c < "$home/boot-new.img");
head -c "$newsize" "$savedir/boot-after.img" > "$home/boot-readback-prefix.img";
cmp -s "$home/boot-new.img" "$home/boot-readback-prefix.img" || abort "Boot write verification failed. Restore boot-before.img.";
cp /tmp/recovery.log "$savedir/recovery-after.log" 2>/dev/null;
sha256sum "$savedir/boot-before.img" "$savedir/boot-after.img" > "$savedir/SHA256SUMS";
sync;
ui_print "Boot write verified. Keep Rikka-rescue for rollback and diagnosis.";
