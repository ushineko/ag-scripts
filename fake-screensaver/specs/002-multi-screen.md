# Spec 002: Multi-Screen Support

**Status: COMPLETE**

## Description
Support for blanking specific screens or all screens.

## Requirements
- `--screen` flag to specify screen indices
- Default to blanking all screens
- Display available screen indices on run

## Acceptance Criteria
- [x] `--screen 0 2` blanks specific screens
- [x] No argument blanks all screens
- [x] Shows available screen indices in terminal

## Implementation Notes
Added in v1.1.0. Screen selection via command-line argument.
