# Spec 002: Priority Auto-Switching

**Status: COMPLETE**

## Description
Automatically switch to highest-priority connected device when devices connect/disconnect.

## Requirements
- Monitor device connection state
- Auto-switch to highest priority device when current disconnects
- Support "Connect on Select" for Bluetooth devices

## Acceptance Criteria
- [x] Auto-switch triggers on device disconnect
- [x] Selects highest-priority connected device
- [x] Clicking offline Bluetooth device triggers auto-connect
- [x] Notifications via notify-send on auto-switch

## Implementation Notes
Priority-based auto-switching implemented with Bluetooth auto-connect on select.
