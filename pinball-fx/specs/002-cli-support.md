# Spec 002: CLI Support

**Status: COMPLETE**

## Description
Command-line interface for scripted/automated use.

## Requirements
- `--screen` flag to target specific screen
- `--uninstall` flag to remove rules

## Acceptance Criteria
- [x] `--screen 0` targets screen by index
- [x] `--uninstall` removes KWin rules
- [x] Works alongside interactive menu

## Implementation Notes
CLI arguments parsed in configure_kwin.py.
