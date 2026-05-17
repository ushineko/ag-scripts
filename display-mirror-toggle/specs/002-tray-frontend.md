# Spec 002: Tray Frontend (v1.1.0)

> **Note**: This work has no associated issue tracker ticket. ag-scripts is a personal monorepo with no ticket system (see project CLAUDE.md).

## Overview

Add a PyQt6 system-tray frontend to display-mirror-toggle. The tray reflects the live mirror state, exposes Toggle / Enable / Disable / Settings from the context menu, persists a JSON config, and registers a global hotkey via KDE's KGlobalAccel D-Bus interface. The existing `display-mirror-toggle.sh` remains the canonical engine — the tray shells out to it rather than reimplementing kscreen-doctor logic.

## Problem Statement

The v1.0 CLI is fine for hotkey binding but provides no visual indication of the current mirror state. Toggling via a hotkey gives no feedback unless the user happens to be looking at the OLED. A tray icon with state-reflecting iconography and notify-send on state changes closes that feedback loop and adds in-app configuration (source/replica pair and the global hotkey itself) without forcing the user to edit shell config or remember CLI flags.

## Requirements

### Functional Requirements

- [x] System-tray icon that reflects current mirror state (active / inactive / outputs-absent), themed via `QIcon.fromTheme` with fallbacks
- [x] Read-only status label in the menu showing `Mirror: ON/OFF (source → replica)`
- [x] Context menu actions: `Toggle now`, `Enable mirror`, `Disable mirror`, `Settings…`, `About`, `Quit`
- [x] Left-click on tray icon toggles the mirror
- [x] `Enable mirror` is disabled when already active; `Disable mirror` is disabled when already inactive
- [x] Settings dialog edits source connector, replica connector, and global hotkey (Qt key sequence)
- [x] Global hotkey registered via `org.kde.kglobalaccel` D-Bus (KDE Plasma 6), live-rebound on Settings save
- [x] Empty hotkey clears the binding
- [x] Hotkey-triggered toggles fire the same action path as menu/click toggles
- [x] Periodic background poll (default 5s) so the icon stays in sync if state changes from outside the tray
- [x] Single-instance guard via `QLocalSocket` — second launch shows a notification balloon and exits cleanly
- [x] `notify-send` desktop notification when the mirror state actually flips (not on no-op enable/disable); tray-balloon fallback when notify-send isn't on PATH
- [x] Persistent JSON config at `~/.config/display-mirror-toggle/config.json` (schema: source, replica, global_hotkey, poll_interval_seconds, version)
- [x] Graceful degradation when KGlobalAccel is not reachable (non-KDE session): config still saves, no binding is registered, Settings dialog shows an explanatory hint

### Non-Functional Requirements

- [x] PyQt6 only; system Python (`/usr/bin/python3`)
- [x] Engine logic stays in `display-mirror-toggle.sh` — the tray subprocesses it. No duplication of kscreen-doctor logic in Python.
- [x] Engine is invoked with `--source` / `--replica` from config so changes to those connectors apply without restarting the tray
- [x] Status parsing degrades safely (returns inactive) when the engine script is missing or returns non-zero
- [x] Tests do not require a running KDE session or kscreen-doctor — engine tests use a stubbed `.sh`
- [x] Module follows audio-source-switcher / vpn-toggle structural patterns (package layout, single-instance, config manager)
- [x] KGlobalAccel wrapper modeled on `vscode-launcher/global_shortcut.py` (the production-tested reference)

### Installer Requirements

- [x] `install.sh` installs CLI symlink, tray launcher symlink, applications `.desktop`, and autostart `.desktop` (idempotent)
- [x] `.desktop` `Exec=` line rewritten to point at the actual checkout path
- [x] `uninstall.sh` stops any running tray process, removes all four artifacts, and accepts `--purge-config` to wipe `~/.config/display-mirror-toggle/`
- [x] `pkill` pattern in uninstaller matches both the `.py` entry script and symlink-launched processes (`display-mirror-tray(\.py)?`)

### Documentation Requirements

- [x] README updated with tray section, hotkey behavior, config schema example
- [x] Version bumped to 1.1.0 in `__init__.py` and README
- [x] Changelog entry for v1.1.0

### Tests

- [x] `tests/test_config.py` — round-trip, defaults, partial config merge, corrupt JSON fallback
- [x] `tests/test_engine.py` — status parsing (active / inactive / absent), failure handling, missing-script handling, argument forwarding
- [x] Existing `tests/test_display_mirror_toggle.sh` still passes (13/13)

## Design Notes

- The tray polls the engine via subprocess on a `QTimer` — KGlobalAccel does not signal "screen config changed", and `kscreen-doctor -j` is also a one-shot read, so polling is the simplest sync mechanism. 5-second cadence is fast enough to feel responsive and slow enough to be invisible in `top`.
- `MirrorEngine.status()` parses human-readable output rather than `kscreen-doctor -j` directly. Reason: keeping all kscreen-doctor parsing in one place (the `.sh`) means a single ANSI-stripping path and a single set of edge cases to maintain. The shell tests already cover the parser.
- Notifications compare `before.active` to `after.active` rather than trusting engine output. A future engine refactor can change wording without breaking notification fidelity, and idempotent no-ops naturally don't notify.
- The Settings dialog applies hotkey rebind *before* persisting other changes, so a failed bind (combo already in use) doesn't leave the saved config out of sync with the live binding — same pattern vscode-launcher uses.

## Acceptance Criteria

- [x] All Functional Requirements satisfied
- [x] All Non-Functional Requirements satisfied
- [x] All Installer Requirements satisfied
- [x] All Documentation Requirements satisfied
- [x] All Tests Requirements satisfied
- [x] Tray smoke-tested on live KDE Plasma 6 session: icon appears, status reflects real `kscreen-doctor` state, toggle/enable/disable work, notify-send fires on state change
- [x] Installer + uninstaller exercised end-to-end on njv-cachyos

## Status: COMPLETE
