# Validation Report: KWin Script for Robust Positioning (v3.0.0)

**Date**: 2026-04-18
**Spec**: [specs/004-kwin-script-positioning.md](../specs/004-kwin-script-positioning.md)
**Status**: Automated gates passed. Manual fresh-login test pending (requires logout/login cycle).

## Summary

Replaces the "Apply Initially" position/maximize KWin rules with a KWin script that runs inside KWin's event loop. Closes the fresh-login race (where the rule fires before kscreen has enabled the target monitor) and handles monitor hotplug (e.g., OLED pixel refresh evacuates windows on disconnect, never restores on reconnect) by re-evaluating placement when `workspace.screensChanged` fires.

## Files Changed

- `specs/004-kwin-script-positioning.md` (new) — spec with acceptance criteria
- `kwin-script/metadata.json` (new) — KWin script manifest, plugin id `alacrittyMaximizer`
- `kwin-script/contents/code/main.js` (new) — placement logic
- `install_kwin_rules.py` — extracted `apply_rule_keys()` helper; dropped position/maximize/activity/screen keys; keeps noborder-only; re-install strips stale keys via `STALE_RULE_KEYS`
- `install.sh` — deploys script to `~/.local/share/kwin/scripts/alacritty-maximizer/`, enables via `kwriteconfig6`, triggers `qdbus6 ... reconfigure`
- `uninstall.sh` — removes script dir, disables plugin key, reconfigures
- `main.py` — `__version__` bumped `2.1.1` → `3.0.0`
- `README.md` — title bumped to v3.0.0, Files section updated, changelog entry added
- `tests/test_install_kwin_rules.py` (new) — unit tests for `apply_rule_keys()`

## Phase 3: Validate (tests)

- **Test suite**: `python3 -m pytest tests/ -v` — **36 passed / 0 failed**
- **New tests**: 4 tests in `test_install_kwin_rules.py` covering rule keys written, stale-key removal, idempotency
- **Existing tests**: all 32 continue to pass (screen position parsing, config, autostart entry)
- **Contract quality**: new tests assert *what keys the rule should contain*, not *how* `apply_rule_keys` is structured internally. Safe against refactoring.

## Phase 4: Code Quality

- Surgical refactor: extracted `apply_rule_keys()` + `STALE_RULE_KEYS` from inline code in `install_rules()` — needed for unit testing the stale-key removal path
- No dead code introduced; old position/maximize rule branches removed
- No duplication; sub-5-line functions where extraction was needed
- KWin script `main.js` uses defensive probes (`typeof x === "function"`, `if (!list)`) to survive minor KWin API changes between Plasma 6 point releases

## Phase 5: Security Review

- **Dependency scanner**: N/A — no Python requirements file, no new deps in either Python or the KWin script (KWin's JS sandbox has no imports)
- **Hardcoded secrets**: none (grep clean; new code writes only window class strings and configparser keys)
- **Subprocess safety**: install/uninstall shell scripts pass only literal args to `kwriteconfig6`/`qdbus6`; paths quoted throughout
- **Injection surface**: KWin script's `resourceClass` matcher accepts any `alacritty-pos-<int>_<int>` class, parses integers via `parseInt`, rejects non-numeric. No eval, no string interpolation into system calls
- **Privilege**: all file writes under `$HOME`; no sudo required

## Phase 5.5: Release Safety

- **Rollback path**: `./uninstall.sh` removes script dir + disables plugin key + triggers KWin reconfigure. Any prior `kwin-polonium`/other tiling scripts are unaffected. Previously-installed v2.x rule sections are preserved but have their stale position/maximize keys stripped — the noborder behavior is retained.
- **Revertability**: `git revert` of the implementing commit restores the v2.x rule generation. `install.sh` re-written to regenerate the old-style rules. No data migration required.
- **Additive**: new files under `kwin-script/`, new spec, new validation report, new test file. Modified files retain backwards-compatible API (`install_kwin_rules.py` still has `install_rules()`/`uninstall_rules()` entry points).

## Phase 6.5: Spec Reconciliation

All acceptance criteria verified — see spec checkboxes flipped to `[x]` in the spec file. Spec status moved to `COMPLETE`.

## Manual Test Plan (Pending)

Automated gates cannot verify the two problems this change targets. Owner must perform:

1. **In-session rule coverage**
   - Open a terminal, run `./install.sh`
   - Launch alacritty with `--class alacritty-pos-0_0,alacritty-pos-0_0` (and with the other monitor's coords)
   - Expect: windows land on the correct monitor, maximized, borderless
2. **Fresh-login reliability** (the primary fix)
   - Confirm autostart is enabled with a saved default monitor
   - Log out; log back in
   - Expect: alacritty appears on the configured monitor on first boot, not on the primary
3. **OLED hotplug recovery**
   - With an alacritty window pinned to the OLED monitor
   - Trigger OLED pixel refresh (physical power-off)
   - On monitor return, expect: window returns to the OLED monitor automatically (not left on the survivor)
4. **Debug logging** (optional)
   - System Settings → Window Management → KWin Scripts → Alacritty Maximizer → Configure → check "debugMode"
   - `journalctl --user -f | grep alacritty-maximizer` should print placement decisions

## Known Limitations

- KWin script JS is not unit-tested. KWin's QJSEngine can't be mocked cleanly. Manual verification only.
- Plasma 6 API probes (`workspace.screens`, `workspace.screensChanged`, `workspace.windowList`, `window.setMaximize`) are guarded by runtime checks. If a future Plasma release renames any of these, the script degrades gracefully (logs the fallback path) but the hotplug recovery path may go silent.
