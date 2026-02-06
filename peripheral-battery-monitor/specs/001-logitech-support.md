# Spec 001: Logitech Mouse Support

**Status: COMPLETE**

## Description
Fetch battery levels for Logitech mice via solaar.

## Requirements
- Use solaar libraries for precise battery levels
- Support Unifying and Bolt receivers
- Display percentage in UI

## Acceptance Criteria
- [x] Uses solaar for battery level fetching
- [x] Supports Unifying/Bolt receivers
- [x] Displays battery percentage in dashboard
- [x] Fixed dbus/systemd resource exhaustion (v1.1.1)
- [x] Fixed battery staleness after state transitions (v1.3.3)

## Implementation Notes
Logitech support via solaar. Resource fix added in v1.1.1 with caching.
State transition fix added in v1.3.3 - always pings device before reading battery.
