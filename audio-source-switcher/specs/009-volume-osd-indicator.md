# Spec 009: On-Screen Volume Indicator (OSD)

> **Note**: This work has no associated issue tracker ticket. This is a personal public repository that does not use an issue tracker (see project CLAUDE.md).

## Status: COMPLETE

## Executive Summary

Replace the per-keypress `notify-send` volume popups with a self-owned on-screen
display (OSD): a frameless panel centered on the active monitor that appears on
volume change, updates in place on rapid repeat presses, and auto-hides after a
short delay. The running tray application owns the single OSD widget, so repeated
volume operations coalesce into one updating window instead of a stack of
notifications.

## Context

The current volume path (`cli.py::handle_volume_command`) is a stateless one-shot:
each global-hotkey press spawns a fresh `audio-source-switcher --vol-up/--vol-down`
process, adjusts the (JamesDSP-aware) sink volume, fires `notify-send`, and exits.
Because each press is a separate process, nothing owns a persistent, updating
indicator. The `synchronous:volume` hint is supposed to collapse Plasma
notifications, but the desired UX is a dedicated centered OSD under our control.

`VolumeMonitorThread` (`controllers/pipewire.py`) and `MainWindow.check_and_sync_volume`
already exist but are currently unwired dead code. The single-instance
`QLocalServer` ("ag_audio_source_switcher") already brokers GUI focus hand-off and
is the natural transport for volume commands.

## Design

- **Owner**: the already-running tray instance owns one `VolumeOSD` widget. Hotkey
  CLI invocations forward `VOL_UP`/`VOL_DOWN` over the existing local socket; the
  live instance performs the smart volume change and shows/updates the OSD.
- **All-changes trigger**: `VolumeMonitorThread` (`pactl subscribe`) is wired up so
  the OSD also appears for volume changes originating anywhere (mixer, other apps,
  media keys), mirroring the system OSD. Subscribe events are debounced (~80 ms)
  and filtered by comparing against the last-shown volume so non-volume sink events
  and self-triggered changes do not double-fire.
- **Fallback**: when no instance is running, the CLI keeps today's behavior
  (inline smart volume change + `notify-send`).
- **Wayland realities** (verified on this machine, KDE/Wayland, Qt 6.10):
  - `Qt.ToolTip` surfaces fail to map without a transient parent — not usable.
  - A frameless `Qt.Tool` window maps, but Wayland gives clients no control over
    absolute position or stacking, so centering + keep-above must come from a
    KWin rule (consistent with repo pattern in `alacritty-maximizer`,
    `foghorn-leghorn`, etc.).
  - KDE default placement is not centered, and the two monitors differ in size and
    orientation, so centering is computed per screen.
- **KWin rule**: `install_kwin_rule.py` writes one rule per screen matched by the
  OSD's per-screen window title (all app windows share one Wayland app_id, so title
  is the only per-window discriminator), forcing centered `position`, `above`,
  `noborder`, `skiptaskbar`, `skipswitcher`, and `skippager`. Uninstall removes them.

## Requirements

- A `VolumeOSD` frameless widget of fixed size showing a volume-fill bar, the
  percentage, and a muted state.
- The running instance shows/updates the single OSD on: (a) `VOL_UP`/`VOL_DOWN`
  socket messages, and (b) any real volume change seen via `pactl subscribe`.
- Rapid repeat operations update the existing OSD and restart its hide timer rather
  than spawning new windows.
- Smart (JamesDSP-aware) target resolution is shared between the in-app path and the
  CLI fallback (no duplicated logic).
- `install_kwin_rule.py` installs/uninstalls per-screen centered + keep-above rules;
  wired into `install.sh` and `uninstall.sh`.
- CLI `--vol-up`/`--vol-down` forward to the running instance when present and fall
  back to inline change + `notify-send` when not.

## Acceptance Criteria

- [x] `VolumeOSD` widget renders a fill bar, percentage text, and a muted state at a
      fixed size; frameless `Qt.Tool` with translucent background.
      (`gui/osd.py`; styled to KDE Oxygen Dark per user request.)
- [x] The running instance owns exactly one `VolumeOSD`; repeated shows update it in
      place and restart a single auto-hide timer (~1.5 s).
      (`MainWindow.setup_volume_osd`; `test_osd_updates_in_place_and_restarts_timer`.)
- [x] `--vol-up`/`--vol-down` forward `VOL_UP`/`VOL_DOWN` over the local socket when
      an instance is running; the instance applies the smart volume step and shows
      the OSD with the new value. (`cli.py` + `MainWindow.handle_volume_hotkey`;
      verified live: 36% → 41% → 36% on the JamesDSP-resolved sink.)
- [x] When no instance is running, `--vol-up`/`--vol-down` fall back to inline smart
      volume change + `notify-send` (today's behavior preserved).
      (`cli.handle_volume_command`; `test_cli_falls_back_to_notify_when_no_instance`.)
- [x] `VolumeMonitorThread` is wired; a volume change from any source shows the OSD,
      with debounce + last-value comparison preventing double-fires and non-volume
      sink events being ignored. (`setup_volume_osd` + `_process_volume_event`;
      `test_process_volume_event_dedups_unchanged`; live signal verified.)
- [x] Smart target resolution (JamesDSP retarget) is factored into a single shared
      code path used by both the in-app and CLI-fallback flows. (`volume.py`.)
- [x] `install_kwin_rule.py` writes per-screen rules forcing centered position +
      keep-above + noborder + skiptaskbar (matched by OSD window title) and removes
      them with `--uninstall`; invoked from `install.sh`/`uninstall.sh`.
      (`test_kwin_rule.py`; verified live — rules in sections 26/27.)
- [x] Tests cover: OSD show/update-in-place + timer restart, socket message parsing
      to the volume-adjust path, subscribe debounce/last-value filtering, and KWin
      rule install/uninstall idempotency. (13 new tests, all passing.)
- [x] README + About dialog version updated (v13.0, user-approved).

## Risks & Assumptions

- **KWin title matching on Wayland**: the OSD is matched by window title because all
  app windows share one app_id. If title matching is unreliable on a given KWin
  build, centering/keep-above degrade; the widget still sets frameless + stay-on-top
  Qt hints and calls `move()` as best-effort fallback (effective on X11/other DEs).
- **Subscribe noise**: `pactl subscribe` fires on many sink events; the last-value
  comparison filters non-volume changes. Volume changes from the app's own slider
  will also surface the OSD (acceptable — mirrors system OSD behavior).
- **Rollback**: additive feature. Revert the commit to restore pure `notify-send`
  behavior; `uninstall.sh --... ` / `install_kwin_rule.py --uninstall` removes the
  KWin rules. No data migration.
- **Integration boundary**: this touches PipeWire/PulseAudio (pactl/pw-link) and the
  KWin compositor — verified empirically on the target machine rather than mocked
  where feasible (manual OSD smoke test documented in validation report).

## Alternatives Considered

- Dedicated OSD daemon (separate systemd user service): rejected — the tray app is a
  persistent process already; a second process adds install/maintenance surface for
  no gain.
- Per-invocation transient OSD from the CLI: rejected — separate processes cannot
  merge/update a shared window, reintroducing the flooding problem in window form.
- `LayerShellQt` (the protocol Plasma's own OSD uses): rejected for now — heavier,
  possibly-absent dependency; KWin rules achieve centered + above with the toolkit
  already in use.
