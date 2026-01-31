# Spec 002: fstab Entry Generator

**Status: COMPLETE**

## Description
Generate fstab entries for data drives labeled DataN or System.

## Requirements
- Scan block devices via lsblk
- Filter by label pattern (Data\d+ or System)
- Skip removable and USB devices
- Generate proper mount options for gaming (Steam/Proton)

## Acceptance Criteria
- [x] Scans block devices and filters by label
- [x] Skips removable/USB devices
- [x] Generates fstab lines with uid/gid/umask
- [x] Output can be appended to /etc/fstab
- [x] Proper NTFS/exFAT mount options

## Implementation Notes
Created `generate_data_mounts.py`. Outputs UUID-based entries for stability.
