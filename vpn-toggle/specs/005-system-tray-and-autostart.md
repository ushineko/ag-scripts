# Spec 005: System Tray, Autostart & Connection Restore (v3.2)

**Status**: COMPLETE

## Overview

Add system tray integration so VPN Toggle can run in the background when the window is closed, provide autostart-on-login support via XDG Autostart, and automatically restore VPN connections on startup.

## Motivation

The monitor thread runs health checks continuously, but closing the window kills the process. Users who want always-on VPN monitoring need the app to persist in the background. A system tray icon provides the standard UX pattern for this on Linux desktops.

Additionally, after a reboot or app restart, VPN connections are lost. The app should remember which VPNs were connected and restore them on startup, ensuring the user's desired VPN state is always maintained. Combined with autostart, this makes VPN monitoring fully hands-off after initial setup.

## Requirements

### System Tray Icon

1. **Tray icon**: Show a `QSystemTrayIcon` using the existing SVG icon on app startup
2. **Context menu** (right-click on tray icon):
   - **Show / Hide**: Toggle main window visibility
   - **Monitor Mode**: Checkable item, mirrors the Monitor Mode checkbox state
   - Separator
   - **Quit**: Full application exit (stops monitor thread, saves geometry, exits process)
3. **Left-click / double-click**: Toggle main window visibility (show if hidden, hide if visible)
4. **Tray tooltip**: Show app name and brief status (e.g., "VPN Monitor - Monitoring 2 VPNs")

### Close-to-Tray Behavior

5. **Window close** (`closeEvent`): When the tray icon is active, hide the window instead of quitting. Save geometry before hiding.
6. **Quit action**: The only way to fully exit is via the tray context menu "Quit" or a new "Quit" option (see below)
7. **Fallback**: If `QSystemTrayIcon.isSystemTrayAvailable()` returns False (e.g., headless / tiling WM without tray), fall back to current behavior (close = quit)

### Quit from Window

8. **File menu or toolbar**: Add a "Quit" button/menu item to the main window that triggers a full quit (same as tray "Quit"). This ensures users can still fully exit without the tray context menu.

### Autostart on Login

9. **XDG Autostart**: Provide a toggle (checkbox in Settings dialog) to enable/disable autostart
10. **When enabled**: Copy/create a `.desktop` file to `~/.config/autostart/vpn-toggle-v2.desktop` with the launch command
11. **When disabled**: Remove the autostart `.desktop` file
12. **Start minimized option**: When autostart is enabled, add an option to start minimized to tray (hidden window). This is controlled via a `--minimized` CLI flag.
13. **Persist preference**: Store autostart and start-minimized preferences in `config.json` under a new `"startup"` key

### VPN Connection Restore on Startup

14. **Track connected VPNs**: Persist a list of VPN connection names that the user has connected (either manually via the GUI or that were already active) in `config.json` under `"startup.restore_vpns"` (list of strings)
15. **Update on state change**: When a VPN is connected (via the app's Connect/Bounce buttons or detected as active by the status timer), add it to the restore list. When a VPN is explicitly disconnected via the app's Disconnect button, remove it from the list. Do NOT remove from the list when the VPN drops due to network issues (that's what the monitor is for).
16. **Restore on startup**: On app launch, iterate the restore list and call `connect_vpn` for each VPN that is not already active. Run this after the monitor thread is set up so the monitor can immediately begin health-checking restored connections.
17. **Restore toggle**: Add a checkbox in Settings to enable/disable connection restore (default: enabled when autostart is enabled, disabled otherwise). Stored in `config.json` as `"startup.restore_connections"`.
18. **Logging**: Log each restore attempt and result to the activity log (e.g., "Restoring VPN: Las Vegas... Connected" or "Restoring VPN: Las Vegas... Already active")

### CLI Flag

19. **`--minimized`**: When passed, start with the window hidden (only tray icon visible). Used by the autostart desktop file.

### Installer / Uninstaller Updates

20. **install.sh**: No changes needed for the tray itself. Autostart is managed at runtime by the app.
21. **uninstall.sh**: Remove `~/.config/autostart/vpn-toggle-v2.desktop` if it exists

## Acceptance Criteria

- [ ] System tray icon appears on app startup (when tray is available)
- [ ] Right-click context menu has Show/Hide, Monitor Mode toggle, separator, Quit
- [ ] Left-click on tray icon toggles window visibility
- [ ] Closing window hides it to tray instead of quitting (when tray available)
- [ ] "Quit" from tray menu or window fully exits the application
- [ ] Autostart checkbox in Settings creates/removes `~/.config/autostart/vpn-toggle-v2.desktop`
- [ ] Start minimized checkbox in Settings controls `--minimized` flag in autostart desktop file
- [ ] `--minimized` CLI flag starts the app with window hidden
- [ ] Preferences persisted in `config.json` under `"startup"` key
- [ ] uninstall.sh removes autostart desktop file
- [ ] Falls back to normal close behavior when system tray is unavailable
- [ ] All existing tests pass
- [ ] New tests for tray setup, autostart config, and --minimized flag

## Config Schema Addition

```json
{
  "startup": {
    "autostart": false,
    "start_minimized": false
  }
}
```

## Autostart Desktop File Template

```ini
[Desktop Entry]
Type=Application
Name=VPN Toggle
Comment=VPN connection manager and health monitor
Exec=vpn-toggle-v2 --minimized
Icon=vpn-toggle-v2
Terminal=false
Categories=Network;
X-GNOME-Autostart-enabled=true
```

When `start_minimized` is false, the `Exec` line omits `--minimized`.

## Implementation Notes

- `QSystemTrayIcon` lives in `PyQt6.QtWidgets`
- The existing `icon.svg` is rendered to QIcon with multiple resolutions in `vpn_toggle_v2.py` — reuse that QIcon for the tray
- The tray icon and context menu should be set up in `VPNToggleMainWindow` since it owns the monitor thread lifecycle
- Pass the QIcon into the main window constructor so it can be used for both the window and the tray
- The `closeEvent` change is the most critical behavioral change — it must be tested carefully
- For the "Monitor Mode" context menu item, connect its `toggled` signal bidirectionally with the existing `monitor_checkbox`

## Files to Modify

| File | Changes |
|------|---------|
| `vpn_toggle_v2.py` | Add `--minimized` flag, pass QIcon to main window |
| `vpn_toggle/gui.py` | System tray setup, closeEvent change, context menu, Quit button, autostart settings |
| `vpn_toggle/config.py` | Add `startup` config defaults and getter/setter |
| `uninstall.sh` | Remove autostart desktop file |
| `tests/test_gui.py` | Tests for tray setup, close-to-tray, autostart toggle |
| `tests/test_config.py` | Tests for startup config |
| `README.md` | v3.2 documentation |

## Out of Scope

- Custom tray icon states (e.g., different icon when VPN is connected vs disconnected) — can be a future enhancement
- Windows/macOS support — this is Linux-only (XDG Autostart, NetworkManager)
- KDE-specific tray behaviors beyond what Qt handles automatically
