# Spec 002: Keychron Keyboard Support

**Status: COMPLETE**

## Description
Support for Keychron keyboards in multiple connection modes.

## Requirements
- Bluetooth: Fetch battery via upower
- Wired: Detect USB connection, show "Wired" status
- Wireless (2.4G): Detect receiver, show "Wireless" status

## Acceptance Criteria
- [x] Bluetooth mode shows battery percentage via upower
- [x] Wired mode detected and displayed
- [x] 2.4G wireless mode detected (battery unavailable)
- [x] Connection mode displayed in UI

## Implementation Notes
Keychron K4 HE support. Enhanced in v1.0.1 for multi-mode detection.
