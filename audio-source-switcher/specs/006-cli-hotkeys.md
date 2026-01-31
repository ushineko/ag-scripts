# Spec 006: CLI & Global Hotkeys

**Status: COMPLETE**

## Description
Command-line control for global hotkey integration on Wayland.

## Requirements
- CLI flags for device connection and volume control
- Context menu to copy hotkey commands
- Smart volume routing to hardware (bypassing JamesDSP)

## Acceptance Criteria
- [x] `--connect` flag switches to device by name
- [x] `--vol-up` and `--vol-down` flags for volume control
- [x] Context menu "Copy Hotkey Command" option
- [x] Volume changes show OSD feedback
- [x] Documentation for KDE Plasma shortcut setup

## Implementation Notes
Added in v11.1. CLI control for Wayland hotkey compatibility.
