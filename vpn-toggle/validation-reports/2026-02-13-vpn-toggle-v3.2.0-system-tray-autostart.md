## Validation Report: VPN Toggle v3.2.0 - System Tray, Autostart & Connection Restore
**Date**: 2026-02-13
**Status**: PASSED

### Phase 3: Tests
- Test suite: `python -m pytest tests/ -v`
- Results: 143 passing, 0 failing
- New tests: 24 (8 config startup, 6 system tray, 5 autostart, 5 VPN restore)
- Status: PASSED

### Phase 4: Code Quality
- Dead code: Pre-existing unused `AssertDetail` import in graph.py (not introduced by this change)
- Duplication: None found
- Encapsulation: Tray logic in VPNToggleMainWindow (owns lifecycle), autostart file management in SettingsDialog, config startup methods in ConfigManager
- Refactorings: Cleaned up `Dict`/`List` type hints to lowercase generics in config.py and gui.py
- Status: PASSED

### Phase 5: Security Review
- No new external input handling (all changes are internal config and UI)
- No secrets or credentials involved
- Autostart `.desktop` file constructed from controlled strings (binary path via `shutil.which`, no user input in Exec line)
- VPN restore uses existing `connect_vpn` which calls `_run_nmcli` with parameterized args (no injection risk)
- `config.json` restore_vpns list stores VPN connection names already known to NetworkManager
- Status: PASSED

### Phase 5.5: Release Safety
- Change type: Code-only (UI behavior changes, new config section)
- Pattern used: Additive (new config key `startup` with defaults, new CLI flag `--minimized`, new UI elements)
- Backward compatible: Existing configs without `startup` key get merged with defaults automatically
- Rollback plan: Revert commit, redeploy. Autostart .desktop file can be manually removed from `~/.config/autostart/`
- Status: PASSED

### Changes Summary

#### System Tray (gui.py)
- Added `QSystemTrayIcon` setup in `setup_tray()` with context menu (Show/Hide, Monitor Mode, Quit)
- Left-click/double-click toggles window visibility
- Tooltip shows active VPN count, updated on status timer
- Fallback: `_tray_available` flag when `isSystemTrayAvailable()` returns False

#### Close-to-Tray (gui.py)
- `closeEvent` hides window when tray available (sets `event.ignore()`)
- `_quitting` flag distinguishes close-to-tray from actual quit
- Quit only via tray menu "Quit", window "Quit" button, or `quit_application()` method

#### Autostart (gui.py)
- `SettingsDialog` expanded with Startup Settings group (autostart, start minimized, restore connections)
- `apply_autostart()` creates/removes `~/.config/autostart/vpn-toggle-v2.desktop`
- Start minimized option toggles `--minimized` in Exec line

#### VPN Connection Restore (gui.py, config.py)
- `_restore_vpn_connections()` called on startup, iterates restore list and connects inactive VPNs
- `on_connect` adds to restore list; `on_disconnect` removes from restore list
- `update_status` adds VPN to restore list when first detected as active (handles external connections)
- Network drops do NOT remove from restore list (only explicit disconnect does)

#### Config (config.py)
- Added `startup` section to `DEFAULT_CONFIG` with autostart, start_minimized, restore_connections, restore_vpns
- Added `get_startup_settings()`, `update_startup_settings()`, `get_restore_vpns()`, `add_restore_vpn()`, `remove_restore_vpn()`

#### Entry Point (vpn_toggle_v2.py)
- Added `--minimized` CLI flag
- Pass `app_icon` and `start_minimized` to VPNToggleMainWindow constructor
- Window only shown when not `--minimized`

#### Uninstaller (uninstall.sh)
- Removes `~/.config/autostart/vpn-toggle-v2.desktop` if present

#### Version & Docs
- Version bumped to 3.2.0 in `__init__.py`, `gui.py` window title
- README updated with v3.2 section, CLI options, and changelog entry
- Spec 005 marked COMPLETE

### Overall
- All gates passed: YES
