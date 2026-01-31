# Spec 001: Read-Only Mount Fix

**Status: COMPLETE**

## Description
Detect and repair NTFS mounts that have fallen into read-only mode.

## Requirements
- Scan DataN and System mount points
- Detect read-only mounts via findmnt
- Run ntfsfix to clear dirty flags
- Remount and verify write access

## Acceptance Criteria
- [x] Scans `/mnt/Data*` and `/mnt/System*` mount points
- [x] Detects read-only status via findmnt
- [x] Runs `ntfsfix -d` to clear dirty flags
- [x] Remounts and verifies write access
- [x] Requires root privileges

## Implementation Notes
Created `fix_readonly_mounts.py`. Common issue after improper shutdowns in dual-boot.
