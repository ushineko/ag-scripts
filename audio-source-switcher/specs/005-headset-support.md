# Spec 005: Headset Support

**Status: COMPLETE**

## Description
Support for SteelSeries Arctis headsets via headsetcontrol.

## Requirements
- Display battery percentage when connected via USB
- Detect disconnected state for auto-switching
- Configure "Disconnect on Idle" timeout

## Acceptance Criteria
- [x] Battery percentage displayed in device list
- [x] Disconnected state detected when powered off
- [x] Idle timeout configuration in UI (1-90 mins)
- [x] Uses headsetcontrol for communication

## Implementation Notes
Arctis Nova Pro Wireless support via headsetcontrol. Headset Settings section added in v11.4.
