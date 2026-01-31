# Spec 001: Migration Runbook

**Status: COMPLETE**

## Description
Automated runbook for migrating CachyOS between NVMe drives.

## Requirements
- Wipe target drive, partition, format
- Transfer all BTRFS subvolumes via send/receive
- Use stable /dev/disk/by-id paths for safety

## Acceptance Criteria
- [x] Wipes and partitions target drive
- [x] Formats with BTRFS
- [x] Transfers subvolumes via btrfs send/receive
- [x] Uses /dev/disk/by-id paths (not /dev/nvmeXnY)
- [x] Safety documentation for destructive operations

## Implementation Notes
Created `migration_runbook.sh`. v1.1.0 added stable device paths for safety.
