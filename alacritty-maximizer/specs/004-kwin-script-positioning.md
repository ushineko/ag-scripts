# Spec 004: KWin Script for Robust Positioning

## Status: INCOMPLETE

## Description

Replace the "Apply Initially" position/maximize KWin rules from Spec 002 with a KWin script that runs inside KWin's event loop. This eliminates the fresh-login race condition (rule fires before target monitor is online) and handles monitor hotplug (e.g., OLED pixel refresh) by re-evaluating placement when screens change.

## Problem

Current behavior uses `positionrule=4` (Apply Initially) and `maximizevert/horizrule=4`. At fresh login, `X-KDE-autostart-phase=2` fires the wrapper before kscreen has finished bringing up secondary monitors, so the rule matches but KWin places the window on whatever monitor is available at that instant. Rule never re-fires, so the window stays on the wrong screen. On OLED pixel-refresh hotplug, KWin evacuates windows on monitor disconnect and does not restore them on reconnect — same root cause (no re-evaluation path).

## Requirements

- KWin script handles placement + maximize for windows with `resourceClass` matching `alacritty-pos-<X>_<Y>`.
- On `windowAdded`: parse X,Y from class; find the screen whose geometry contains that point; `sendClientToScreen` + `setMaximize(true, true)`. If no screen matches (target not online yet), do nothing.
- On `screensChanged`: re-evaluate all existing windows matching the class prefix and re-place any whose current screen does not match the target.
- Configurable debug logging (default off) via `readConfig("debugMode", false)`.
- `install_kwin_rules.py` reduced to install only the `noborder`/`noborderrule=2` rule as a fallback (positioning/maximize moved to script).
- `install.sh` deploys the KWin script to `~/.local/share/kwin/scripts/alacritty-maximizer/`, enables it via `kwriteconfig6`, and reconfigures KWin.
- `uninstall.sh` disables the script, removes the script directory, and removes the noborder rule.
- Version bumped to 3.0.0 in `main.py` and `README.md`.

## Acceptance Criteria

- [x] `kwin-script/metadata.json` and `kwin-script/contents/code/main.js` exist and are valid
- [x] Script matches windows by `resourceClass.startsWith("alacritty-pos-")` and parses the X_Y suffix
- [x] Script iterates `workspace.screens` (or equivalent) to find the screen containing (X, Y)
- [x] Script calls `workspace.sendClientToScreen` and `window.setMaximize(true, true)` on match
- [x] Script listens to `workspace.screensChanged` (or equivalent) and re-evaluates matching windows
- [x] Debug logging gated on `readConfig("debugMode", false)`, emits to `console.debug` with prefix
- [x] `install_kwin_rules.py` no longer writes `position`, `positionrule`, `maximizevert`, `maximizevertrule`, `maximizehoriz`, `maximizehorizrule`, `activity`, `activityrule` keys — only `noborder` and `noborderrule` remain
- [x] Uninstaller cleans up noborder rules (existing behavior preserved) AND removes `~/.local/share/kwin/scripts/alacritty-maximizer/` AND sets `alacrittyMaximizerEnabled=false` in `kwinrc`
- [x] `install.sh` deploys the script and enables it; `qdbus6 ... reconfigure` is called once after all install steps
- [x] `main.py` `__version__` = `3.0.0`
- [x] README version references updated to 3.0.0 with changelog entry for this change
- [x] Unit tests added for any Python code paths changed (class-name parsing is now a no-op in Python — tests for `install_kwin_rules.py`'s rule shape)
- [x] Validation report created under `validation-reports/`
- [ ] Manual test: fresh login places alacritty window on the configured monitor on first try (requires logout/login cycle — user action)

## Non-Goals

- Unit-testing the KWin script itself. KWin's JS runtime cannot be mocked cleanly; manual verification only.
- Replacing the Python autostart launcher. The wrapper still launches alacritty with the `alacritty-pos-X_Y` class; the script consumes that class.
- Handling the case where the user has the same X coordinate on two monitors (e.g., vertical monitor stacks). Current `pos-X_Y` naming includes Y so this isn't a concern.

## Implementation Notes

- Plasma 6 API confirmed from reference script: `workspace.windowAdded.connect(window => ...)`, `window.resourceClass`, `window.resizeable && window.moveable && window.moveableAcrossScreens`, `window.screen` (integer index), `workspace.sendClientToScreen(window, idx)`, `workspace.clientArea(KWin.MaximizeArea, window)`, `window.frameGeometry.{x,y,width,height}`.
- `window.setMaximize(horizontally, vertically)` — to be verified at test time; if it doesn't exist in Plasma 6, fall back to writing `window.frameGeometry` to cover the MaximizeArea rect.
- `workspace.screens` shape and `screensChanged` signal name to be verified against runtime; if the exact signal differs, fall back to polling `workspace.numScreens` via `virtualScreenGeometryChanged` or similar.
- KWin script metadata `X-Plasma-API=javascript`, `X-Plasma-MainScript=code/main.js`, `KPackageStructure=KWin/Script`.
