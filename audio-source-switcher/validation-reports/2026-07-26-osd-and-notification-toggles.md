## Validation Report: OSD and Notification Toggles (v13.1)

**Date**: 2026-07-26
**Version**: 13.0 -> 13.1
**Spec**: `specs/010-osd-and-notification-toggles.md`

## Summary

Adds two Settings checkboxes — "Show volume OSD" and "Notify on device switch" —
persisted as `osd_enabled` and `switch_notifications`. Both default to enabled, so
upgrading changes nothing until a box is unticked. Failure notifications bypass the
notification toggle so a switch that did not work is never silent.

## Changes

### Code
- `audio_source_switcher/config.py`: added a module-level `DEFAULTS` map including
  `osd_enabled` and `switch_notifications`. `load_config` now deep-copies `DEFAULTS`
  and merges the persisted file over it, replacing a default dict literal that was
  duplicated in two places and an ad hoc `mic_links` backfill. A missing, malformed,
  or partial config yields fully-populated defaults.
- `audio_source_switcher/gui/main_window.py`:
  - Two `QCheckBox` widgets in the Settings group with explanatory tooltips,
    initialized from config, wired to `on_osd_toggled` / `on_notifications_toggled`,
    which persist immediately (same pattern as `on_auto_switch_toggled`).
  - `_show_osd` returns before showing when `osd_enabled` is false, but still records
    `_last_osd_volume` so the `pactl subscribe` dedup stays accurate and re-enabling
    mid-session does not replay a stale value.
  - `send_notification` gained `informational: bool = True` and returns early when
    informational and `switch_notifications` is false.
  - The four failure call sites (two "Switch Failed", "Connection Failed",
    "Connection Timeout") pass `informational=False`.
  - About dialog version 13.0 -> 13.1.
- `audio_source_switcher/cli.py`: new `_osd_enabled()` helper; the no-instance
  fallback `notify-send` (which stands in for the OSD) is gated on it. The volume
  change itself is unaffected.

### Tests
- `test_settings_toggles.py` (new, 20 tests).
- `test_volume_osd.py`: `_bare_main_window` now sets `win.config = {}` (the helper's
  fake instance needs the attribute `_show_osd` reads); the CLI fallback test patches
  `_osd_enabled` so it no longer depends on the developer's real config file.

### Docs
- `README.md` (sub-project): v13.1 changelog, a "Switchable Indicators" feature
  bullet, and a Configuration table documenting both keys and their defaults.
- Root `README.md`: descriptions are version-free and still accurate; not changed.

## Why

KDE Plasma 6.7.3 changed what the stock volume OSD does on this machine. Verified on
the bus: `kded6`'s `audioshortcutsservice` (from `plasma-pa`) calls
`org.kde.osdService.volumeChanged` on `plasmashell` for volume changes from *any*
source, including this app's own `pactl` writes — the volume keys are still released
from kmix, so it is not a shortcut conflict. It also now reports the physical sink
rather than `jamesdsp_sink`: changing the bluez sink 47% -> 48% made Plasma's OSD
report 48, while changing `jamesdsp_sink` 55% -> 56% left it reporting 48. The stock
OSD reading a pinned-at-100% `jamesdsp_sink` was the original reason spec 009 built a
replacement, so the premise has changed — but it may change back on a future Plasma
update, so the indicators are made switchable rather than removed.

## Validation

### Phase 3: Tests
- `pytest` in `audio-source-switcher/` (system python 3.14, `QT_QPA_PLATFORM=offscreen`):
  **43 passed**, 0 failed. 20 of those are new.
- New coverage: defaults contain both keys enabled; missing-file load; backfill of a
  pre-010 config without clobbering persisted values; persisted `false` not overridden
  by defaults; mutable defaults not aliased across loads; malformed JSON falls back to
  defaults; OSD suppressed / shown / defaulted-on; `_last_osd_volume` still recorded
  while suppressed; hotkey and subscribe paths both respect the toggle; informational
  notification suppressed / sent / defaulted-on; failure notification sent while
  notifications are off, both via the helper and via the real
  `on_cli_connect_finished` failure path; both toggle handlers persist; CLI fallback
  skips `notify-send` while still performing the volume change.
- **Live integration** (target machine, KDE Plasma 6.7.3 / Wayland):
  - App restarted on the new code from the repo checkout (`install.sh` symlinks to it,
    so no reinstall was needed). Clean start, empty log, no traceback.
  - The user unticked both boxes in the running app. The config file was rewritten
    with `"osd_enabled": false` and `"switch_notifications": false` while
    `device_priority`, `mic_links`, `auto_switch`, `window_geometry`, and
    `loopback_enabled` all survived — the `DEFAULTS` merge and save round-tripped a
    pre-010 config in the real app, not just in tests.
  - OSD suppression verified with `kdotool`: from a confirmed baseline of 0 windows
    matching `ass-volume-osd`, `--vol-up`/`--vol-down` changed the volume (bluez sink
    58% -> 48%) with the window count staying **0** across 1.5s of polling. An earlier
    reading of 1 came from a stale window shown before the toggle and was invalidated
    by re-running from a clean baseline.
  - Loopback unaffected: it is owned by `audio-loopback.service`, so
    `_restore_loopback_from_config` correctly skipped it across the restart (no
    duplicate `pw-loopback`); the unit stayed `active`.
  - The restart also dropped a leaked `CLAUDECODE=1` that the previously-running
    instance had inherited.

### Phase 4: Code Quality
- Removed duplication: one `DEFAULTS` map replaces two copies of the default dict
  literal plus the `mic_links` special case.
- Each toggle has exactly one guard, at the single existing choke point
  (`_show_osd`, `send_notification`), so no call site needs to know about the setting.
- The two new handlers are two lines each and mirror `on_auto_switch_toggled`;
  extracting a generic setter for three trivial methods would diverge from the
  established idiom for no gain.
- No dead code introduced. `ruff` and `flake8` on the changed files are clean; the two
  repo-wide findings (`MagicMock` unused in `test_headset_control.py`, the deliberate
  `_app` handle in `cli.py`) are pre-existing and untouched.

### Phase 5: Security
- **Dependency scan**: `pip-audit` 2.10.0 against `/usr/lib/python3.14/site-packages`.
  One finding — `msgpack` 1.1.2 (GHSA-6v7p-g79w-8964, fixed in 1.2.1). It is the
  pacman-managed `python-msgpack` system package and is **not** used by this project
  (no `msgpack` import anywhere in the tree). This change adds **zero** dependencies.
- **Secrets**: none. Grep of the diff for password/secret/token/key/credential
  patterns returned nothing.
- **Injection (A03)**: no new `subprocess` invocation. `notify-send` is still called
  with list args (no `shell=True`), and the new config values are booleans used only
  in `if` conditions — never interpolated into a command.
- **Deserialization / data integrity (A08)**: config is `json.load` only (no pickle,
  no eval). A non-dict or malformed top level raises inside the existing `try` and
  falls back to defaults, covered by `test_load_config_unreadable_file_falls_back_to_defaults`.
  Unknown keys in the file are merged but only ever read by explicit name.
- **Insecure design (A04)**: considered and rejected making the toggle silence failure
  notifications — a failed switch must stay visible. Hence the `informational` split.
- **A05**: defaults are the pre-existing behavior, so an upgrade cannot silently
  disable a user's only failure signal.

### Phase 5.5: Release Safety
- **Rollback**: `git revert` restores unconditional OSD and notifications. The two
  extra JSON keys are ignored by v13.0's `load_config`, so a downgrade needs no config
  cleanup and loses nothing.
- **Additive**: yes. Two new keys, two new widgets, one new optional parameter with a
  behavior-preserving default. No removals, no signature breaks for existing callers.
- **Blast radius**: single-user desktop app. No network, database, or shared state.

## Known Limitations

- **Enabled-path OSD rendering** is covered by unit tests
  (`test_show_osd_shows_when_enabled`, `test_show_osd_defaults_to_shown_when_key_absent`
  exercise the real `_show_osd`) and by the v13.0 live verification, not by a fresh
  on-screen check in this round — the user had already switched the OSD off, and
  flipping it back would have required restarting their tray app twice to reload the
  in-memory config.
- **Toggles apply to the running instance immediately** because the handler mutates
  the in-memory config, but editing `config.json` by hand does **not** affect a running
  instance; that requires a restart. The CLI fallback (`_osd_enabled`) reads from disk
  per invocation and so is unaffected.
- **Out of scope**: why Plasma stopped reading `jamesdsp_sink`, and why `jamesdsp_sink`
  currently sits at 55% rather than the 100% the switcher's sync path pins it to. Both
  are recorded in the sysadmin notes.

## Status

All quality gates passed. Spec 010 reconciled (all AC checked, Status COMPLETE).
Ready to commit.
