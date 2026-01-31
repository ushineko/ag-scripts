# Spec 004: AirPods BLE Support

**Status: COMPLETE**

## Description
Advanced BLE scanning for AirPods battery status.

## Requirements
- Fetch Left/Right/Case battery levels via BLE
- Support disconnected device monitoring
- Fallback logic for unreliable BLE data

## Acceptance Criteria
- [x] BLE scanning for AirPods manufacturer data
- [x] Displays L/R/Case battery levels
- [x] Works when disconnected from system audio
- [x] Fallback logic for missing data
- [x] Relaxed RSSI threshold (-85) for reliability

## Implementation Notes
Added in v1.2.0. Uses python-bleak for BLE. 30-second refresh interval.
