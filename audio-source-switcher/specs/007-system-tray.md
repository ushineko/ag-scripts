# Spec 007: System Tray

**Status: COMPLETE**

## Description
System tray integration with minimize-to-tray and notifications.

## Requirements
- Minimize to tray on close
- Notifications on auto-switch
- About menu item

## Acceptance Criteria
- [x] Window minimizes to tray on close
- [x] Tray icon shows current status
- [x] Notifications sent via notify-send
- [x] About menu item in tray context menu
- [x] Window size restored when opening from tray

## Implementation Notes
System tray with PyQt6. About dialog added in v11.3, window size fix in v11.2.
