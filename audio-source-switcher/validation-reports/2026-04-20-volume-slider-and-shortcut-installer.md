## Validation Report: Volume Slider Fix + Shortcut Installer Conveniences (v12.1)

**Date**: 2026-04-20
**Version**: 12.0 -> 12.1

## Summary

Fixes a long-standing bug where clicking the volume slider groove (or using arrow keys / mouse wheel) did not apply the change, and adds two installer conveniences to make binding volume hotkeys (e.g. a USB volume knob, Meta+Numpad+/-) reliable across machines.

## Changes

### Code
- `audio_source_switcher/gui/main_window.py`:
  - `on_vol_slider_changed`: now also applies the volume when `isSliderDown()` is False (catches groove-clicks, keyboard arrows, mouse wheel). During drag, `isSliderDown()` stays True so only the label updates.
  - `on_vol_slider_released`: delegates to new helper `_apply_slider_volume` for drag-release case.
  - `_apply_slider_volume(val)`: extracted shared push-to-pactl path.
  - Slider range: `setRange(0, 100)` -> `setRange(0, 150)` to match backend clamp.
  - About dialog version bumped to 12.1.

### Installer
- `install.sh`:
  - Adds `~/.local/bin/audio-source-switcher` symlink to `audio_source_switcher.py` (also `chmod +x` on the script). Makes CLI invocations portable for KDE custom shortcuts.
  - New `--bind-volume-keys` flag: idempotently releases Plasma's kmix `increase_volume` / `decrease_volume` active bindings (sets to `none,<default>,<label>`). Saves originals to `~/.config/audio-source-switcher/volume-keys-backup.ini` on first run; subsequent runs preserve the backup and only re-assert the 'none' state.
  - `--help` usage text added.
- `uninstall.sh`:
  - Removes `~/.local/bin/audio-source-switcher` symlink.
  - Auto-restores Plasma volume bindings from backup if marker file `~/.config/audio-source-switcher/volume-keys-bound` is present (full uninstall).
  - New `--unbind-volume-keys` flag: restores only the Plasma bindings, leaves the app installed.
  - Backup + marker + state dir cleaned up on restore.

### Docs
- `README.md` (sub-project): Added v12.1 changelog entry. Rewrote "Override System Volume Shortcuts" section to document the new `--bind-volume-keys` flag and the `audio-source-switcher` CLI symlink. Noted the cosmetic Plasma-OSD-at-100% behavior.

## Why

- **Slider bug**: `sliderReleased` only fires for handle drags, not for `QAbstractSlider::triggerAction()` events (groove click, page step, keyboard). Users expected click-to-jump to work like every other slider.
- **Installer flag**: Binding a custom shortcut to `Volume Up` / `Volume Down` requires clearing kmix's default grab first, and doing that in the GUI has to be repeated per machine. Making it a reproducible `install.sh` flag (with an auto-restore uninstaller) turns it into a durable setting.
- **Symlink**: KDE custom shortcuts stored the command with a hardcoded absolute path, which broke across machines and required editing to move. `~/.local/bin/audio-source-switcher` is stable.

## Validation

### Phase 3: Tests
- `pytest` in `audio-source-switcher/`: **7 passed**, 0 failed.
  - `test_headset_control.py`: 1 test
  - `test_mic_association.py`: 6 tests
- Manual: User confirmed slider click-on-groove / keyboard / wheel now work as expected.

### Phase 4: Code Quality
- Reviewed diffs. Extracted duplicated push-to-pactl path into `_apply_slider_volume` helper (removed one-off duplication in `on_vol_slider_released`).
- `install.sh`: removed a dead `[ "$rest" = "$current" ] && rest="$current"` no-op line; simplified to inline parameter expansion `"none,${current#*,}"` with a comment explaining the no-comma edge.
- `uninstall.sh`: `restore_volume_keys` function extracted so both the standalone flag path and full-uninstall path share the logic.
- No dead code; no long methods; no duplication.

### Phase 5: Security
- **Dependency scan**: `pip-audit --local` — 10 CVEs reported, all in `aiohttp 3.13.3`. Verified via `grep -r 'aiohttp'` that this project does not import or depend on aiohttp. Findings are noise from unrelated packages in the system Python environment.
- **Secrets**: No hardcoded credentials, tokens, or keys in changed code.
- **Injection**: `kwriteconfig6`/`kreadconfig6` arguments are quoted; no shell interpolation of user-controlled values. Backup file values are read via `IFS='=' read -r` and passed as literal arguments, never eval'd or executed.
- **File ops**: All paths rooted under `$HOME`; `ln -sfn` target resolved via `cd "$(dirname "$0")" && pwd` which handles symlinks and spaces safely.
- **OWASP Top 10 review**: no new exposure. A03 (injection) and A08 (data integrity) were the relevant categories — both clear.

**Tool used**: `pip-audit` 2.9.0 (from `/usr/bin/pip-audit`).

### Phase 5.5: Release Safety
- **Rollback**: `git revert` on the commit. Volume-key rebinding has in-band rollback via `./uninstall.sh --unbind-volume-keys`.
- **Additive**: Yes. No breaking removals. Default `./install.sh` (no flag) behaves as before plus the new symlink (a clean additive artifact, cleaned up by `uninstall.sh`).
- **Blast radius**: single-user desktop; no network, shared-state, or DB surface.

## Known Limitations

- `--bind-volume-keys` requires a logout/login (or Plasma restart) for `kglobalaccel` to pick up the change. An attempted D-Bus reload was removed because `org.kde.KGlobalAccel.reloadConfig` does not exist on Plasma 6; the installer prints a note to that effect.
- The custom shortcut creation (Step 2: bind `Volume Up` -> `audio-source-switcher --vol-up`) still requires a one-time manual action in **System Settings -> Shortcuts**. `khotkeysrc` uses UUID-keyed entries that are impractical to hand-write reliably.
- Plasma's own audio OSD (plasma-pa) still pops up showing `jamesdsp_sink` at 100% whenever any sink changes. This is a cosmetic artifact of using JamesDSP as a fixed-unity default sink. Documented in the README.

## Testing Gaps

- The `--bind-volume-keys` flag's end-to-end effect (USB knob triggers CLI after custom shortcut is bound) was not tested in this session because the user could not log out. User will verify later.

## Status

All quality gates passed. Ready to commit.
