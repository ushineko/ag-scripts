## Validation Report: VPN Toggle v3.1.0 - UX Improvements
**Date**: 2026-02-13
**Status**: PASSED

### Phase 3: Tests
- Test suite: `python -m pytest tests/ -v`
- Results: 119 passing, 0 failing
- New tests: 9 (2 graph DateAxisItem, 3 connection timestamp, 4 connection time UI)
- Status: PASSED

### Phase 4: Code Quality
- Dead code: Pre-existing unused `AssertDetail` import in graph.py (not introduced by this change)
- Duplication: None found
- Encapsulation: Connection time logic properly encapsulated in VPNWidget; NM timestamp fetch in VPNManager
- Refactorings: None needed
- Status: PASSED

### Phase 5: Security Review
- No new external input handling (all changes are display/UI logic)
- No secrets or credentials involved
- `get_connection_timestamp` uses existing `_run_nmcli` with parameterized args (no injection risk)
- Status: PASSED

### Phase 5.5: Release Safety
- Change type: Code-only (UI display changes)
- Pattern used: N/A (additive changes, no breaking modifications)
- Rollback plan: Revert commit, redeploy
- Status: PASSED

### Changes Summary

#### Graph X-Axis (graph.py)
- Replaced relative offset X values (seconds from first point) with Unix epoch timestamps
- Added `pg.DateAxisItem` for human-readable time labels (HH:MM auto-formatted)
- Updated `_update_vpn_plot` and `_add_bounce_markers` to use epoch timestamps
- Removed `base_time` parameter from `_add_bounce_markers`

#### Connection Time Counter (gui.py, vpn_manager.py)
- Added `VPNManager.get_connection_timestamp()` to fetch activation time from NM
- Added `_connected_since` tracking to `VPNWidget` with cached NM timestamp
- Added `connection_time_label` to VPN widget header (DD:HH:MM:SS format)
- Added `update_connection_time()` method for per-second counter updates
- Added 1-second `QTimer` in `VPNToggleMainWindow` for connection time ticks

#### Version & Docs
- Version bumped to 3.1.0 in `__init__.py`, `gui.py` window title
- README updated with v3.1 section and changelog entry

### Overall
- All gates passed: YES
