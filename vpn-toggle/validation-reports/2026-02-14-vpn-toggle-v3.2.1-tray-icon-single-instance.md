## Validation Report: VPN Toggle v3.2.1 - Tray Icon Fix & Single-Instance Guard
**Date**: 2026-02-14
**Status**: PASSED

### Phase 3: Tests
- Test suite: `python -m pytest tests/ -v`
- Results: 149 passing, 0 failing
- New tests: 6 (4 single-instance QLocalServer/QLocalSocket, 2 tray icon_path)
- Status: PASSED

### Phase 4: Code Quality
- Dead code: Pre-existing unused `AssertDetail` import in graph.py (not introduced by this change)
- Duplication: None found
- Encapsulation: Single-instance logic in entry point (vpn_toggle_v2.py), tray icon rendering in VPNToggleMainWindow.setup_tray()
- Refactorings: None needed
- Status: PASSED

### Phase 5: Security Review
- No new external input handling
- QLocalServer/QLocalSocket uses Unix domain sockets with default permissions (user-only)
- No secrets or credentials involved
- No injection risk (socket name is a compile-time constant)
- Status: PASSED

### Phase 5.5: Release Safety
- Change type: Code-only (bugfixes)
- Pattern used: Additive (new QLocalServer/QLocalSocket IPC, new icon_path parameter with default None)
- Backward compatible: Existing VPNToggleMainWindow callers work without icon_path parameter
- Rollback plan: Revert commit, redeploy
- Status: PASSED

### Changes Summary

#### Tray Icon Fix (vpn_toggle_v2.py, gui.py)
- Resolved `__file__` symlinks via `Path(__file__).resolve()` so icon loads when launched from `~/.local/bin` symlink
- Added 22x22 pixmap size for KDE tray compatibility
- Pass `icon_path` (SVG file path) to VPNToggleMainWindow
- In `setup_tray()`, construct QIcon from SVG file path (`QIcon(str(path))`) and set via `setIcon()` after construction for reliable KDE/SNI D-Bus rendering

#### Single-Instance Guard (vpn_toggle_v2.py)
- QLocalSocket connects to `vpn-toggle-v2` socket on startup
- If connection succeeds: another instance running → send "show" message → exit
- If connection fails: create QLocalServer, listen on socket
- Server's `newConnection` signal triggers `window.show()` / `raise_()` / `activateWindow()`
- Stale sockets cleaned up via `QLocalServer.removeServer()` before listen

### Overall
- All gates passed: YES
