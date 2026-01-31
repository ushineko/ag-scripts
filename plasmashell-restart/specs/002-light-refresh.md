# Spec 002: Light Refresh Mode

**Status: COMPLETE**

## Description
Refresh shell in-place via D-Bus without process restart.

## Requirements
- Send D-Bus message to refresh shell
- Faster for minor visual glitches
- `--refresh` flag to activate

## Acceptance Criteria
- [x] `-r`/`--refresh` flag available
- [x] Sends D-Bus refresh message
- [x] No process restart required
- [x] Faster than full restart

## Implementation Notes
Light refresh mode added in v1.1.0 for minor glitches.
