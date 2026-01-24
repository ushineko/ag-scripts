# The Great CachyOS Move - Implementation Plan

## Goal
Migrate the running CachyOS installation from `/dev/sdd` (SATA SSD) to `/dev/nvme1n1` (NVMe 4TB), changing the partitioning scheme to GPT with a dedicated EFI partition and a single Btrfs partition filling the rest.

## Current State
- **Source**: `/dev/sdd`
    - `sdd1`: EFI (VFAT)
    - `sdd2`: Btrfs (`/`, `/home`, etc.)
- **Destination**: `/dev/nvme1n1` (Currently NTFS, `Data1`)
- **Bootloader**: `systemd-boot`
- **Filesystem**: Btrfs on source, targeted for destination.

## Proposed Strategy: "Live" Migration via Btrfs Send/Receive
Since the source is Btrfs and the target will be Btrfs, we can use `btrfs send` / `btrfs receive` which is safer and more reliable for live systems than `rsync`. It preserves attributes, UUIDs (internally), and data consistency if snapshots are used.

### 1. Preparation (Dry-Run / Investigatory Phase)
- **Investigatory Script**: A script to inventory the current state and validatethe destination.
    - Validate destination drive (`nvme1n1`) presence and size.
    - Inventory installed packages (Native vs AUR).
    - List current btrfs subvolumes used for system and home.
    - Generate a "Runbook" of commands that will be executed.
    - **Safety Check**: Verify destination is empty if mounted. If relevant files exist, ABORT.
    - **Config Check**: Verify destination is NOT in `/etc/fstab`. If found, ABORT.

### 2. Execution (Planned Future Steps - NOT executed yet)
1. **Partitioning**:
    - Wipe `/dev/nvme1n1`.
    - Create GPT label.
    - Create Partition 1: 1024MB, Type `ef00` (EFI System).
    - Create Partition 2: Remaining space, Type `8300` (Linux Filesystem).
2. **Formatting**:
    - Format P1 as FAT32 (`mkfs.vfat -F32 -n CachyOS-EFI`).
    - Format P2 as Btrfs (`mkfs.btrfs -L CachyOS-NVMe`).
3. **Cloning (The "Kick" Step)**:
    - Mount Destination Top-Level (ID 5) to `/mnt/migration_pool`.
    - Detect ALL active subvolumes (root, home, cache, log, etc.).
    - Loop through each subvolume:
        - Snapshot source (e.g., `/@root` -> `/@root.migration`).
        - Send/Receive to `/mnt/migration_pool`.
        - Rename correctly on destination (e.g. remove .migration suffix).
    - Unmount `/mnt/migration_pool`.

4. **Staging for Config**:
    - Mount new `@` subvolume to `/mnt/new_root`.
    - Iterate other subvolumes (`@home`, `@root`, etc.), create their mountpoints in `/mnt/new_root`, and mount them.
    - Mount EFI partition to `/mnt/new_root/boot`.
5. **Post-Processing**:
    - **Fstab**: Generate new fstab for destination using new UUIDs.
    - **Bootloader**:
        - Mount new EFI partition to `/mnt/new_root/boot` (or `/mnt/new_root/efi` depending on layout).
        - Install `systemd-boot`: `bootctl install --path=/mnt/new_root/boot`.
        - Create loader entry pointing to new root UUID.
    - **Chroot & Re-init**:
        - Chroot into `/mnt/new_root`.
        - Re-generate initramfs (`mkinitcpio -P`).

### 3. Verification Plan
The Investigatory Script (`pre_move_check.py`) will serve as the verification of readiness.
It will:
1. Verify source is Btrfs.
2. Verify destination device ID matches expected (checking model/size).
3. Check for sufficient space.
4. Output the exact sequence of commands for the user to review.
5. **Strict Safety Check**: If destination is mounted, ensure it is completely empty. Fail otherwise.
6. **Config Check**: Ensure destination device is not listed in `/etc/fstab` to prevent cloning invalid configuration.

### Post-Migration Verification (Included in Runbook)
The runbook includes a final verification block that will:
1. Extract the new UUID of the NVMe root partition.
2. Grep the new `/mnt/new_root/etc/fstab` to ensure it uses the correct UUID.
3. Grep the new loader entries in `/mnt/new_root/boot/loader/entries` to ensure they point to the correct UUID.
If these checks verify, the system is safe to reboot.
