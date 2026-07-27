# Spec 010: OSD and Notification Toggles

> **Note**: This work has no associated issue tracker ticket. This is a personal public repository that does not use an issue tracker (see project CLAUDE.md).

## Status: COMPLETE

## Executive Summary

Makes the app's two self-owned indicators switchable: a "Show volume OSD" and a
"Notify on device switch" checkbox in Settings, persisted as `osd_enabled` and
`switch_notifications` and both defaulting to enabled, so upgrading changes nothing
until a box is unticked. Failure notifications bypass the notification toggle. The
prompt was KDE Plasma 6.7.3 now driving its own volume OSD for changes this app makes
— reviewers should look first at the `informational` split in
`MainWindow.send_notification` (the deliberate choice not to let the toggle silence
failures) and at the `ConfigManager.DEFAULTS` merge, which replaces a default dict
literal that was duplicated in two places and is shared by every other feature.

## Context

The switcher currently shows two things unconditionally:

- its own volume OSD (spec 009), on every volume change, and
- an "Audio Switched" `notify-send` notification whenever the physical sink changes.

Both were built when KDE's own equivalents were either absent or useless. The stock
Plasma volume OSD read `jamesdsp_sink`, which the switcher pins at 100%, so it
displayed a constant, meaningless 100% bar — that is why spec 009 replaced it.

That is no longer true on this machine. Observed on KDE Plasma 6.7.3 / plasma-pa
6.7.3:

- `kded6`'s `audioshortcutsservice` module (shipped by `plasma-pa`) calls
  `org.kde.osdService.volumeChanged` on `plasmashell` for volume changes originating
  from *any* source, including the switcher's own `pactl` writes. The volume keys are
  still correctly released from kmix (`increase_volume=none` / `decrease_volume=none`
  in `kglobalshortcutsrc`), so this is not a shortcut conflict — Plasma is reacting to
  the sink write itself.
- That OSD now reports the *physical* sink's level rather than `jamesdsp_sink`.
  Verified by direct test: changing the bluez sink 47% → 48% made Plasma's OSD report
  48; changing `jamesdsp_sink` 55% → 56% left it reporting 48.

The result is two stacked OSDs for every volume keypress, and comparable duplication
for device-switch notifications. Since the stock behavior is now sometimes correct
and may change again on future Plasma updates, the fix is not to delete the
switcher's own indicators but to make them switchable, so the user can show whichever
set the system is not already providing.

## Design

- **Two config keys**, both defaulting to `true` so existing installs see no behavior
  change on upgrade:
  - `osd_enabled` — the switcher's own volume OSD.
  - `switch_notifications` — informational device-switch notifications.
- **Config defaults are centralized.** `ConfigManager` currently repeats its default
  dict literal in two places and backfills `mic_links` ad hoc. A single `DEFAULTS`
  map, deep-copied per load and merged under the persisted data, replaces both and
  backfills any key added in future without further special-casing.
- **Single choke points.** `MainWindow._show_osd` is the only place the OSD is shown,
  and `MainWindow.send_notification` is the only place `notify-send` is invoked from
  the GUI, so each toggle needs exactly one guard. `_show_osd` still records
  `_last_osd_volume` when suppressed, keeping the subscribe dedup logic correct so
  re-enabling mid-session does not replay a stale value.
- **Informational vs failure notifications.** `send_notification` gains an
  `informational: bool = True` parameter. The toggle suppresses only informational
  notifications ("Audio Switched", "Connecting..."). Failure notifications
  ("Switch Failed", "Connection Failed", "Connection Timeout") pass
  `informational=False` and are always delivered — a switch that silently did not
  work must not be silent.
- **CLI fallback follows `osd_enabled`.** `cli.handle_volume_command`'s no-instance
  fallback fires `notify-send` as a stand-in for the OSD, so it honors the same key.
- **UI placement**: two `QCheckBox` widgets in the existing "Settings" group box,
  following the `auto_switch_cb` pattern (checked from config, `toggled` → handler
  that writes config immediately). Tooltips state why one would turn each off.

## Requirements

- `osd_enabled` and `switch_notifications` config keys, defaulting to enabled, and
  persisted to `~/.config/audio-source-switcher/config.json`.
- A config file written by an older version (lacking these keys) loads with both
  defaulted to enabled rather than raising or disabling the features.
- A "Show volume OSD" checkbox and a "Notify on device switch" checkbox in the
  Settings group, reflecting and immediately persisting the config.
- With `osd_enabled` false, no code path shows the OSD widget — neither the hotkey
  path nor the `pactl subscribe` path — and the CLI no-instance fallback sends no
  `notify-send`.
- With `switch_notifications` false, informational notifications are suppressed while
  failure notifications are still delivered.
- Defaults are defined in exactly one place in `ConfigManager`.
- Tests cover config defaulting/backfill, both suppression paths, the failure-notification
  exemption, and the CLI fallback gate.

## Acceptance Criteria

- [x] `ConfigManager` defines defaults once and returns them merged under persisted
      data, including `osd_enabled: True` and `switch_notifications: True`.
      (`config.py` `DEFAULTS` + `load_config`; `test_defaults_enable_both_toggles`,
      `test_load_config_missing_file_returns_defaults`.)
- [x] A config file missing both keys loads with both enabled, and existing keys in
      the file are not overwritten by defaults.
      (`test_load_config_backfills_old_file_without_toggles`,
      `test_load_config_does_not_override_persisted_false`; also confirmed live — the
      user's pre-010 config gained both keys with `device_priority`, `mic_links`,
      `auto_switch`, `window_geometry`, and `loopback_enabled` intact.)
- [x] Mutable defaults (`device_priority`, `mic_links`) are not shared between loads
      (no aliasing of the module-level default objects).
      (`copy.deepcopy` in `load_config`; `test_load_config_does_not_alias_mutable_defaults`.)
- [x] "Show volume OSD" checkbox appears in the Settings group, initialized from
      `osd_enabled`, and writes the config on toggle. (`main_window.py` Settings group
      + `on_osd_toggled`; `test_osd_toggle_handler_persists`; confirmed live.)
- [x] "Notify on device switch" checkbox appears in the Settings group, initialized
      from `switch_notifications`, and writes the config on toggle.
      (`on_notifications_toggled`; `test_notification_toggle_handler_persists`;
      confirmed live.)
- [x] With `osd_enabled` false, `_show_osd` does not call `VolumeOSD.show_volume` but
      still records `_last_osd_volume`; with it true, the OSD shows as before.
      (`test_show_osd_suppressed_when_disabled`,
      `test_show_osd_still_records_state_when_disabled`,
      `test_show_osd_shows_when_enabled`, plus the hotkey and subscribe path tests;
      verified live with `kdotool` — 0 `ass-volume-osd` windows across a volume change.)
- [x] With `osd_enabled` false, the CLI no-instance fallback performs the volume
      change but sends no `notify-send`. (`cli._osd_enabled`;
      `test_cli_fallback_skips_notify_when_osd_disabled`.)
- [x] With `switch_notifications` false, `send_notification(..., informational=True)`
      sends nothing, and the "Audio Switched" and "Connecting..." call sites are
      informational. (`test_informational_notification_suppressed_when_disabled`;
      both call sites use the `informational=True` default.)
- [x] With `switch_notifications` false, `send_notification(..., informational=False)`
      still sends; the failure call sites pass `informational=False` — two
      "Switch Failed", one "Connection Failed", one "Connection Timeout" (four sites,
      not three as first drafted). (`test_failure_notification_sent_even_when_disabled`,
      `test_connect_failure_path_notifies_with_notifications_off`.)
- [x] Full test suite passes. (43 passed, 0 failed; 20 new.)
- [x] README changelog + feature list and the About dialog updated to v13.1
      (user-approved version).
- [x] Validation report written (project setting: `validation: strict`).
      (`validation-reports/2026-07-26-osd-and-notification-toggles.md`.)

## Risks & Assumptions

- **Rollback**: purely additive. Revert the commit to restore unconditional OSD and
  notifications; the two extra JSON keys are ignored by the previous version's
  `load_config`, so a downgrade needs no config cleanup.
- **Defaults preserve current behavior**: both keys default to enabled, so an upgrade
  changes nothing until the user unticks a box. The duplicate-OSD annoyance is not
  fixed automatically — that is deliberate, since whether Plasma's OSD is correct
  depends on the machine's Plasma version and JamesDSP routing.
- **Config merge refactor**: `ConfigManager.load_config` is shared by every feature.
  The merge must not overwrite persisted values with defaults, and must deep-copy
  mutable defaults; both are covered by acceptance criteria.
- **Assumption — no separate mute path**: mute state reaches the OSD through
  `_show_osd` like volume does, so the OSD toggle covers it. No separate guard needed.
- **Not addressed here**: why Plasma stopped reading `jamesdsp_sink`, and why
  `jamesdsp_sink` is currently sitting at 55% rather than the 100% the switcher's sync
  path pins it to. Both are diagnosed in the sysadmin notes but out of scope for this
  spec, which only makes the switcher's own output switchable.
- **Integration boundary**: the notification path shells out to `notify-send` and the
  OSD path touches PipeWire via `pactl`. The toggles are verified by unit test at the
  guard, plus a live smoke test on the restarted app recorded in the validation report.
