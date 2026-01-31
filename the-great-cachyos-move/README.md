# The Great CachyOS Move

This directory contains scripts used to migrate the CachyOS installation from one NVMe drive to another using `btrfs send/receive`.

## Table of Contents
- [Scripts](#scripts)
- [Critical Warnings](#️-critical-warnings)
- [Changelog](#changelog)

## Scripts

### `migration_runbook.sh`
The main automated runbook for the migration process.
*   **Purpose**: Wipes the target drive, partitions it, formats it, and transfers all BTRFS subvolumes from the live system.
*   **Safety**: Uses `/dev/disk/by-id/...` stable paths to ensure the correct drive is targeted, preventing accidental data loss if device nodes (`/dev/nvme0n1` etc.) swap on boot.

### `pre_move_check.py`
A python script to verify system state before attempting migration (free space, package consistency, etc.).

## ⚠️ Critical Warnings
*   **Data Loss**: `migration_runbook.sh` is destructive. It **wipes** the configured target disk.
*   **Device Paths**: **NEVER** hardcode `/dev/nvmeXnY` in destructive scripts. Always use `/dev/disk/by-id/` to guarantee you are nuking the correct hardware.

## Changelog

### v1.1.0
- Enhanced runbook with stable `/dev/disk/by-id/` device targeting
- Safety improvement to prevent wrong-disk accidents

### v1.0.0
- Initial release
- Automated btrfs send/receive migration runbook
- Pre-migration system check script
