# Spec 002: Pre-Move System Check

**Status: COMPLETE**

## Description
Verify system state before attempting migration.

## Requirements
- Check free space on target
- Verify package consistency
- Generate runbook if checks pass

## Acceptance Criteria
- [x] Checks available disk space
- [x] Verifies package/system state
- [x] Reports issues before migration
- [x] Python script for pre-checks

## Implementation Notes
Created `pre_move_check.py` for pre-migration validation.
