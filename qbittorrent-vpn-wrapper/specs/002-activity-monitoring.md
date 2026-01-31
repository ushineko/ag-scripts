# Spec 002: Activity Monitoring

**Status: COMPLETE**

## Description
Monitor active downloads/uploads via qBittorrent WebUI.

## Requirements
- Poll WebUI for transfer status
- Detect when all transfers are inactive
- Trigger idle shutdown dialog

## Acceptance Criteria
- [x] Polls qBittorrent WebUI on port 8080
- [x] Tracks active downloads/uploads
- [x] Detects idle state
- [x] Triggers shutdown dialog after idle timeout

## Implementation Notes
WebUI polling for activity monitoring. Idle detection triggers auto-shutdown flow.
