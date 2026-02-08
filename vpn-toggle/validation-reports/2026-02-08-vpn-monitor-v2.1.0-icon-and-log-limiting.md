## Validation Report: VPN Monitor v2.1.0 - App Icon and Log Limiting
**Date**: 2026-02-08
**Status**: PASSED

### Changes
1. **Application Icon**: Custom SVG shield icon (green shield with lock motif) set as window icon and installed for desktop launcher
2. **Activity Log Line Limiting**: `append_log` now prunes oldest lines when exceeding 500 lines (`MAX_LOG_LINES`), preventing unbounded memory growth
3. **Installer/Uninstaller**: Updated to install/remove the custom icon at `~/.local/share/icons/vpn-toggle-v2.svg`

### Phase 3: Tests
- Test suite: `python3 -m pytest tests/ -v`
- Results: 70 passing, 0 failing
- New tests: 6 GUI tests for log limiting behavior (`tests/test_gui.py`)
- Status: PASSED

### Phase 4: Code Quality
- Dead code: None found
- Duplication: None found
- Encapsulation: Changes are minimal and well-scoped
- Status: PASSED

### Phase 5: Security Review
- No external input handling changes
- No new dependencies
- SVG icon is static content with no scripts
- Status: PASSED

### Phase 5.5: Release Safety
- Change type: Code-only (additive features)
- Rollback plan: Revert commit, redeploy. Icon is decorative. Log limiting is a pure improvement with no data dependencies.
- Status: PASSED

### Files Modified
- `vpn_toggle/__init__.py` - Version bump to 2.1.0
- `vpn_toggle/gui.py` - Added `MAX_LOG_LINES`, `QTextCursor` import, updated `append_log` with pruning, version in title
- `vpn_toggle/icon.svg` - New SVG icon (green shield with lock)
- `vpn_toggle_v2.py` - Added `Path`, `QIcon` imports, icon loading logic
- `install.sh` - Icon installation, updated version references, custom icon in .desktop file
- `uninstall.sh` - Icon cleanup, updated version references
- `tests/test_gui.py` - New test file with 6 tests for log limiting
- `README.md` - Changelog entry for v2.1.0

### Overall
- All gates passed: YES
