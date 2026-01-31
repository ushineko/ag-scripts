# Spec 001: Full Restart Mode

**Status: COMPLETE**

## Description
Full restart of plasmashell via systemd.

## Requirements
- Use systemctl to restart plasma-plasmashell.service
- Fallback to legacy kquitapp/kstart if needed
- Verify service started successfully

## Acceptance Criteria
- [x] Restarts via systemd (preferred)
- [x] Fallback to kquitapp6/kquitapp5 + kstart
- [x] Verifies successful restart
- [x] Default mode when run without arguments

## Implementation Notes
Full restart added with systemd-first approach in v1.1.0.
