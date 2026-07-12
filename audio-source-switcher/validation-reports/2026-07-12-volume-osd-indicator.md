## Validation Report: On-Screen Volume Indicator (OSD) (v13.0)

**Date**: 2026-07-12
**Version**: 12.1 -> 13.0
**Spec**: `specs/009-volume-osd-indicator.md`

## Summary

Replaces per-keypress `notify-send` volume popups with a self-owned on-screen
display: a frameless panel, styled to KDE Oxygen Dark, centered on the active
monitor. It appears on volume change, updates in place on rapid repeat presses,
and auto-hides after ~1.5s. The running tray instance owns the single OSD widget,
so repeated operations coalesce into one updating window instead of a stack of
notifications. Volume hotkeys forward to the running instance over the existing
single-instance local socket; a `pactl subscribe` monitor also surfaces the OSD
for volume changes from any source. When no instance is running, the CLI falls
back to the previous inline change + `notify-send`.

## Changes

### Code
- `audio_source_switcher/gui/osd.py` (new): `VolumeOSD` frameless `Qt.Tool`
  widget. Oxygen-Dark styling — dark glass gradient panel, soft drop shadow,
  glass top highlight, recessed groove, glossy blue fill (amber >100%, grey
  muted), Oxygen speaker icon via `QIcon.fromTheme`. `show_volume(volume, muted)`
  centers on the cursor's screen, sets a per-screen window title, and restarts a
  single auto-hide timer.
- `audio_source_switcher/volume.py` (new): shared smart-volume helpers
  `resolve_active_sink` (JamesDSP-aware) and `adjust_volume` used by both the
  in-app and CLI-fallback paths.
- `audio_source_switcher/cli.py`: `--vol-up`/`--vol-down` now forward
  `VOL_UP`/`VOL_DOWN` to a running instance over the `ag_audio_source_switcher`
  local socket; fall back to inline `adjust_volume` + `notify-send` otherwise. The
  socket server handles the new messages. `SOCKET_NAME` extracted to a constant.
- `audio_source_switcher/gui/main_window.py`: `setup_volume_osd` owns the OSD and
  wires `VolumeMonitorThread`; `handle_volume_hotkey` applies a smart step and
  shows the OSD; `_process_volume_event` (debounced ~80ms) reads the active sink
  and shows the OSD only when volume/mute actually changed (dedup vs last shown).
  `quit_app` stops the monitor thread.
- `audio_source_switcher/controllers/audio.py`: added `step_sink_volume`
  (relative +/-N%) and `get_sink_mute`.
- `audio_source_switcher/controllers/pipewire.py`: `VolumeMonitorThread` given a
  `stop()` that terminates the `pactl subscribe` subprocess so the thread unblocks
  cleanly on quit (previously unwired dead code).

### Installer
- `install_kwin_rule.py` (new): writes one KWin rule per screen matched by the
  OSD's per-screen window title, forcing centered `position`, `above`, `noborder`,
  `skiptaskbar`, `skipswitcher`, `skippager`. `--uninstall` removes only OSD rules.
- `install.sh`: runs `install_kwin_rule.py` (non-fatal off KDE).
- `uninstall.sh`: runs `install_kwin_rule.py --uninstall`.

### Docs
- `README.md` (sub-project): v13.0 changelog; rewrote the volume-OSD note.
- `README.md` (root): both project tables mention the OSD + KDE Wayland rules.
- About dialog version 12.1 -> 13.0.

## Why

- A one-shot CLI process cannot own a persistent, updating indicator, so the OSD
  is owned by the always-running tray instance and driven over the existing local
  socket. This makes rapid presses coalesce into one window (the core UX goal).
- KDE/Wayland gives clients no control over absolute position or stacking, and
  default placement is not centered; centering + keep-above therefore come from
  KWin rules (the established pattern in `alacritty-maximizer`, `foghorn-leghorn`).

## Validation

### Phase 3: Tests
- `pytest` in `audio-source-switcher/`: **23 passed**, 0 failed.
  - Pre-existing: `test_headset_control.py` (1), `test_mic_association.py` (6).
  - New `test_volume_osd.py` (11): smart-volume resolution/step/no-sink; OSD
    update-in-place + timer restart; per-screen title; subscribe show-on-change +
    dedup; hotkey show; CLI forward-vs-fallback routing.
  - New `test_kwin_rule.py` (6): forced-centered per-screen rule keys; install
    idempotency; foreign-rule preservation; uninstall removes only OSD rules;
    no-file safety.
- **Live integration** (target machine, KDE/Wayland, Qt 6.10):
  - Hotkey -> socket -> instance verified: 36% -> 41% (`--vol-up`) -> 36%
    (`--vol-down`) on the JamesDSP-resolved sink (`CUBILUX` DAC).
  - `pactl subscribe` -> `VolumeMonitorThread` signal fired on a real volume
    change; monitor `stop()` unblocked the thread cleanly.
  - OSD widget maps and paints on the real Wayland display; per-screen centered
    targets correct for both monitors (landscape 2560x1440 -> 1090,1774; portrait
    1440x2560 -> 3090,1214). User visually approved the Oxygen-Dark styling.

### Phase 4: Code Quality
- Smart-volume resolution factored into `volume.py` (previously duplicated between
  `cli.py` and `MainWindow`). No dead code introduced; `VolumeMonitorThread` (dead
  before this change) is now wired and cleanly stoppable. OSD painting split into
  `_paint_shadow` / `_paint_panel` / `_paint_content` helpers. QThread lifecycle
  follows the repo's GC invariants (refs kept on `self`; `stop()` joins via
  `wait()`).

### Phase 5: Security
- **Dependency scan**: `pip-audit --local` (pip-audit 2.10.0). Findings (idna,
  lxml, pillow, msgpack, pip, pygments, pytest, soupsieve) are all in the
  miniforge base environment, not dependencies of this project. The change adds
  **zero new dependencies** (stdlib `subprocess`/`configparser` + already-used
  PyQt6 modules). No project-relevant CVEs.
- **Secrets**: none in changed code (grep for password/secret/token/key/private
  matched only the `screen_token` variable name).
- **Injection (A03)**: all `subprocess` calls use list args (no `shell=True`);
  `direction` is a literal 'up'/'down'; `notify-send` interpolates only an int
  volume. `install_kwin_rule.py` writes computed ints/fixed strings via
  configparser — no user-controlled input. Window titles carry integer screen
  coordinates set via `setWindowTitle` (not a shell).
- **Local socket**: `QLocalServer` accepts `VOL_UP`/`VOL_DOWN`/`SHOW` from the
  same user only; worst case a local same-user process nudges volume or shows the
  window — negligible, and the socket predates this change (only VOL handling
  added).
- **OWASP Top 10**: no new exposure; A03 reviewed and clear. No network/auth/
  deserialization surface.

### Phase 5.5: Release Safety
- **Rollback**: `git revert` restores pure `notify-send` behavior. KWin rules
  removed via `install_kwin_rule.py --uninstall` (also run by `uninstall.sh`).
- **Additive**: yes. New modules + additive controller methods; existing behavior
  preserved as the no-instance fallback. No breaking removals.
- **Blast radius**: single-user desktop; touches PipeWire/PulseAudio (pactl/
  pw-link) and the KWin compositor only. No network, DB, or shared-state surface.

## Known Limitations

- **KWin title matching**: the OSD is matched by window title (all app windows
  share one Wayland app_id). If a KWin build matches titles unreliably, centering/
  keep-above degrade; the widget still sets frameless + stay-on-top hints and
  calls `move()` as a best-effort fallback. Verified working on the target machine.
- **Entry-point interpreter**: `audio_source_switcher.py` uses
  `#!/usr/bin/env python3`. On a shell where miniforge precedes `/usr/bin` in PATH,
  the bare symlink resolves to a conda python without the `dbus` module. The KDE
  session and the `.desktop` (which uses `/usr/bin/python3` explicitly) are
  unaffected. Pre-existing; out of scope for this change.
- **All-source OSD**: the OSD also appears when dragging the app's own volume
  slider (any real volume change surfaces it), mirroring the system OSD.

## Status

All quality gates passed. Spec 009 reconciled (all AC checked, Status COMPLETE).
Ready to commit.
