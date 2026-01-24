#!/bin/bash
# Error Handling Traps
set -e
trap 'echo "[ERROR] Command failed at line $LINENO: $BASH_COMMAND"; exit 1' ERR
echo "[INFO] Starting Migration Runbook..."
# AUTO-GENERATED MIGRATION PLAN - DO NOT RUN BLINDLY
# 1. Wipe and Partition /dev/nvme1n1
# Ensure absolutely nothing is mounted (nuclear option)
fuser -k -m /dev/nvme1n1* || true
sleep 1
umount -R -f /dev/nvme1n1* || true
umount -R -f /mnt/Data1 || true
swapoff /dev/nvme1n1* || true
# Clear signatures (ignore errors if device invalid)
wipefs --all --force /dev/nvme1n1* || true
sgdisk --zap-all /dev/nvme1n1
# Force kernel to drop old partitions (RETRIES)
partprobe /dev/nvme1n1 || true
sleep 2
partprobe /dev/nvme1n1 || true
udevadm settle
sleep 2
# Create new partitions
sgdisk -n 1:0:+1024M -t 1:ef00 -c 1:'CachyOS EFI' /dev/nvme1n1
sgdisk -n 2:0:0 -t 2:8300 -c 2:'CachyOS Root' /dev/nvme1n1
# Sync again
partprobe /dev/nvme1n1
udevadm settle
sleep 5
# Final unmount check before formatting
umount -q /dev/nvme1n1p1 || true
umount -q /dev/nvme1n1p2 || true

# 2. Format Partitions
mkfs.vfat -F32 -n 'CachyOS-EFI' /dev/nvme1n1p1
mkfs.btrfs -L 'CachyOS-NVMe' -f /dev/nvme1n1p2

# 3. Mount Migration Pool (Top Level ID 5)
mkdir -p /mnt/migration_pool
mount -o subvolid=5 /dev/nvme1n1p2 /mnt/migration_pool

# 4. Snapshot and Send (The Migration)
# Process /@
# Cleanup stale snapshot if exists
if [ -d '//_@.migration' ]; then btrfs subvolume delete '//_@.migration'; fi
btrfs subvolume snapshot -r / //_@.migration
btrfs send //_@.migration | btrfs receive /mnt/migration_pool/
mv /mnt/migration_pool/_@.migration /mnt/migration_pool/@
btrfs property set -f -ts /mnt/migration_pool/@ ro false
# Process /@root
# Cleanup stale snapshot if exists
if [ -d '/root/_@root.migration' ]; then btrfs subvolume delete '/root/_@root.migration'; fi
btrfs subvolume snapshot -r /root /root/_@root.migration
btrfs send /root/_@root.migration | btrfs receive /mnt/migration_pool/
mv /mnt/migration_pool/_@root.migration /mnt/migration_pool/@root
btrfs property set -f -ts /mnt/migration_pool/@root ro false
# Process /@cache
# Cleanup stale snapshot if exists
if [ -d '/var/cache/_@cache.migration' ]; then btrfs subvolume delete '/var/cache/_@cache.migration'; fi
btrfs subvolume snapshot -r /var/cache /var/cache/_@cache.migration
btrfs send /var/cache/_@cache.migration | btrfs receive /mnt/migration_pool/
mv /mnt/migration_pool/_@cache.migration /mnt/migration_pool/@cache
btrfs property set -f -ts /mnt/migration_pool/@cache ro false
# Process /@home
# Cleanup stale snapshot if exists
if [ -d '/home/_@home.migration' ]; then btrfs subvolume delete '/home/_@home.migration'; fi
btrfs subvolume snapshot -r /home /home/_@home.migration
btrfs send /home/_@home.migration | btrfs receive /mnt/migration_pool/
mv /mnt/migration_pool/_@home.migration /mnt/migration_pool/@home
btrfs property set -f -ts /mnt/migration_pool/@home ro false
# Process /@tmp
# Cleanup stale snapshot if exists
if [ -d '/var/tmp/_@tmp.migration' ]; then btrfs subvolume delete '/var/tmp/_@tmp.migration'; fi
btrfs subvolume snapshot -r /var/tmp /var/tmp/_@tmp.migration
btrfs send /var/tmp/_@tmp.migration | btrfs receive /mnt/migration_pool/
mv /mnt/migration_pool/_@tmp.migration /mnt/migration_pool/@tmp
btrfs property set -f -ts /mnt/migration_pool/@tmp ro false
# Process /@srv
# Cleanup stale snapshot if exists
if [ -d '/srv/_@srv.migration' ]; then btrfs subvolume delete '/srv/_@srv.migration'; fi
btrfs subvolume snapshot -r /srv /srv/_@srv.migration
btrfs send /srv/_@srv.migration | btrfs receive /mnt/migration_pool/
mv /mnt/migration_pool/_@srv.migration /mnt/migration_pool/@srv
btrfs property set -f -ts /mnt/migration_pool/@srv ro false
# Process /@log
# Cleanup stale snapshot if exists
if [ -d '/var/log/_@log.migration' ]; then btrfs subvolume delete '/var/log/_@log.migration'; fi
btrfs subvolume snapshot -r /var/log /var/log/_@log.migration
btrfs send /var/log/_@log.migration | btrfs receive /mnt/migration_pool/
mv /mnt/migration_pool/_@log.migration /mnt/migration_pool/@log
btrfs property set -f -ts /mnt/migration_pool/@log ro false

# 5. Staging New Root
umount /mnt/migration_pool
mount -o subvol=@,compress=zstd /dev/nvme1n1p2 /mnt/new_root
mkdir -p /mnt/new_root/root
mount -o subvol=/@root,compress=zstd /dev/nvme1n1p2 /mnt/new_root/root
mkdir -p /mnt/new_root/var/cache
mount -o subvol=/@cache,compress=zstd /dev/nvme1n1p2 /mnt/new_root/var/cache
mkdir -p /mnt/new_root/home
mount -o subvol=/@home,compress=zstd /dev/nvme1n1p2 /mnt/new_root/home
mkdir -p /mnt/new_root/var/tmp
mount -o subvol=/@tmp,compress=zstd /dev/nvme1n1p2 /mnt/new_root/var/tmp
mkdir -p /mnt/new_root/srv
mount -o subvol=/@srv,compress=zstd /dev/nvme1n1p2 /mnt/new_root/srv
mkdir -p /mnt/new_root/var/log
mount -o subvol=/@log,compress=zstd /dev/nvme1n1p2 /mnt/new_root/var/log

# 6. Post-Migration Config
mkdir -p /mnt/new_root/boot
mount /dev/nvme1n1p1 /mnt/new_root/boot
genfstab -U /mnt/new_root > /mnt/new_root/etc/fstab
arch-chroot /mnt/new_root bootctl install
arch-chroot /mnt/new_root pacman -S --noconfirm linux-cachyos # Reinstall kernel to regenerate loader entries

# 7. Final Verification
echo 'Verifying UUIDs...'
TARGET_UUID=$(blkid -s UUID -o value /dev/nvme1n1p2)
echo "Target Root UUID: $TARGET_UUID"
echo "Checking /etc/fstab..."
grep $TARGET_UUID /mnt/new_root/etc/fstab && echo 'OK: Found UUID in fstab' || echo 'FAIL: UUID missing in fstab'
echo "Checking Bootloader Entries..."
grep -r $TARGET_UUID /mnt/new_root/boot/loader/entries/ && echo 'OK: Found UUID in bootloader config' || echo 'FAIL: UUID missing in bootloader config'

# Done!
echo "Migration Complete. If verify PASSED, you can reboot."
