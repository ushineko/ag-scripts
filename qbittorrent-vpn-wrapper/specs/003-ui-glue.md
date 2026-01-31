# Spec 003: UI Glue Dashboard

**Status: COMPLETE**

## Description
Status dashboard that attaches to qBittorrent window.

## Requirements
- Use kdotool for window tracking
- Dashboard moves with qBittorrent window
- Display connection status and activity

## Acceptance Criteria
- [x] Uses kdotool for window positioning
- [x] Dashboard glued to top of qBittorrent window
- [x] Moves with main window
- [x] Shows VPN and transfer status

## Implementation Notes
UI glue via kdotool for KDE/Wayland compatibility.
