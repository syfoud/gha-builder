#!/system/bin/sh
# Run immediately after a failed boot in recovery, before another system boot.
set -u
dst=${1:-/sdcard/Rikka-rescue/failure-$(date +%Y%m%d-%H%M%S)}
mkdir -p "$dst" || exit 1
mount -t pstore pstore /sys/fs/pstore 2>/dev/null || true
cp -a /sys/fs/pstore "$dst/" 2>"$dst/pstore-copy-errors.txt" || true
dmesg > "$dst/recovery-dmesg.txt" 2>&1
cat /proc/last_kmsg > "$dst/last_kmsg.txt" 2>&1 || true
cat /proc/cmdline > "$dst/recovery-cmdline.txt"
cat /proc/iomem > "$dst/recovery-iomem.txt"
getprop > "$dst/recovery-properties.txt"
cp /tmp/recovery.log "$dst/" 2>/dev/null || true
ls -l /dev/block/bootdevice/by-name > "$dst/partitions.txt" 2>&1
dd if=/dev/block/bootdevice/by-name/boot of="$dst/failed-boot.img" bs=1048576 2>"$dst/boot-read.txt"
sha256sum "$dst/failed-boot.img" > "$dst/failed-boot.sha256"
sync
echo "Collected: $dst"
