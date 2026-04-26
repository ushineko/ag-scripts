# Spec 004: Heroic-Wrapper Architecture

> **Note**: This work has no associated issue tracker ticket. ag-scripts is a personal monorepo with no tracker per project conventions.

**Status: COMPLETE** (HDR scope dropped in v3.1.0 — see addendum below)

## Addendum (v3.1.0): HDR support removed

The HDR-related ACs in this spec were satisfied by v3.0.0. Subsequent debugging found that HDR through gamescope's WSI layer requires Proton-GE (system wine doesn't propagate `--hdr-enabled` cleanly via wine 11.x's DXVK), but Proton-GE's `winebus.sys` can't disambiguate the controller when Steam Input's virtual XInput pad is also present. v3.1.0 drops HDR support to keep the controller working with system wine. The wrapper no longer sets `ENABLE_GAMESCOPE_WSI=1` / `DXVK_HDR=1` / `--hdr-enabled` and the `PINBALL_FX_NO_HDR` env override is removed. README's recommended Heroic Wine version is now system wine, not Proton.

The mount-namespace fix (bind-mount `/dev/null` over the virtual device's `/dev/input/eventX` inside an `unshare -m -r` namespace) remains a possible future path to restore HDR while keeping the controller working — would warrant its own spec.

## Description

Replace the standalone Python launcher (v2.x) with a tiny gamescope wrapper that Heroic invokes via its per-game "Wrapper Command" setting. Heroic continues to handle Wine/Proton selection, Epic Online Services authentication (so DLC / Pinball Pass content works), and the .desktop menu entry. We just wrap the launch in gamescope + KWin pinning + HDR env.

This is a breaking re-architecture of v2.x. The standalone launcher has fundamental limits — it can't mint Epic auth tokens, so DLC is invisible. Rather than reimplement Epic OAuth, we hand the launch back to Heroic and only wrap the parts Heroic doesn't do (gamescope, monitor placement).

## Requirements

- A bash wrapper script `pinball_fx_wrapper.sh` that:
  - Accepts `wine /path/to/PinballFX.exe <args...>` from Heroic as positional args.
  - Detects the portrait monitor's logical geometry.
  - Installs/refreshes the KWin rule pinning `wmclass=gamescope` to that geometry.
  - Sets HDR env (`ENABLE_GAMESCOPE_WSI=1`, `DXVK_HDR=1`) by default; opt out via `PINBALL_FX_NO_HDR=1`.
  - Execs `gamescope -W <w> -H <h> -w <w> -h <h> -f --hdr-enabled -- <args from Heroic>`.
  - Allows render-resolution override via `PINBALL_FX_WIDTH` / `PINBALL_FX_HEIGHT` env (for 4K rendering on a fractionally-scaled monitor).
- A small Python helper `detect_portrait_screen.py` that prints `<W> <H> <X> <Y>` (logical coords) for the single portrait monitor.
- The existing `install_kwin_rule.py` is unchanged and reused.
- `install.sh` installs the wrapper + helper executables into the project dir, ensures they're chmod'd, and prints the per-game Heroic configuration steps the user must do in the GUI.
- `uninstall.sh` removes the v2.x desktop entry (`PinballFX.desktop`), removes the v1.x desktop entry (`PinballFixer.desktop`), removes any KWin rules (current and legacy), and prints a reminder to also clear the wrapper from Heroic's per-game settings.
- The v2.x standalone Python launcher (`pinball_fx_launch.py`) is deleted.
- Our v2.x `PinballFX.desktop` (and the v1.x `PinballFixer.desktop`) are not installed in v3 — Heroic's own desktop entry is the menu entry.
- Tests retained: `test_install_kwin_rule.py` (KWin rule logic still in use). Tests dropped: `test_launcher.py` (parsing / Proton autodetect / runner-resolution logic no longer exists).
- README documents:
  - The per-game Heroic GUI config: Wine version → GE-Proton 10-29 (or any Proton); Wrapper Command → `<repo>/pinball_fx_wrapper.sh`.
  - The HDR / SDL controller / scaling caveats discovered during v2.x debugging.

## Acceptance Criteria

- [x] `pinball_fx_wrapper.sh` exists, is executable, accepts pass-through args, calls the screen-detect helper, installs the KWin rule, sets HDR env, and execs gamescope wrapping the args.
- [x] `PINBALL_FX_NO_HDR=1` disables `--hdr-enabled` and the HDR env vars.
- [x] `PINBALL_FX_WIDTH` / `PINBALL_FX_HEIGHT` override gamescope's `-W` / `-H` (internal render resolution); the KWin rule and gamescope's `-w` / `-h` (output buffer size) continue to use the detected logical geometry.
- [x] `detect_portrait_screen.py` exits non-zero with a helpful message when zero or multiple portrait monitors are present.
- [x] `install.sh` chmods the wrapper + helper executable, prints the Heroic GUI config steps, and is idempotent.
- [x] `uninstall.sh` removes legacy v1.x and v2.x desktop entries, removes our KWin rule (current and legacy), and is idempotent.
- [x] `pinball_fx_launch.py` is deleted from the repo.
- [x] `PinballFX.desktop` is deleted from the repo.
- [x] `tests/test_launcher.py` is deleted; `tests/test_install_kwin_rule.py` retained and passing.
- [x] README rewritten with the new architecture, Heroic GUI steps, and lessons learned (HDR, controller mapping, KDE scaling caveats); version bumped to 3.0.0.
- [x] Root README pinball-fx row updated.
- [x] Validation report covers tests, lint (pyflakes + shellcheck), OWASP review, dependency scan, and secrets check.

## Out of Scope

- Heroic per-game config edits via JSON. Heroic owns its config; the user does the per-game setup once via the GUI. (Programmatic edits risk being overwritten and aren't worth the fragility for a one-time setup.)
- Steam Input handling. Documented as a caveat (quit Steam before launching) rather than coded around.
- True 4K render with KDE fractional scaling. Documented: either disable scaling on the portrait monitor or set `PINBALL_FX_WIDTH=2160 PINBALL_FX_HEIGHT=3840` and accept gamescope's downscale to the logical 1440×2560 buffer that KWin then upscales back.

## Implementation Notes

- Heroic's per-game wrapper is configured at `~/.config/heroic/GamesConfig/<appid>.json` under `wrapperOptions`. We don't write this — user does it via Heroic GUI.
- Heroic invokes the wrapper as: `<wrapper> wine /path/to/PinballFX.exe <epic auth args...>`. We pass everything after our script verbatim to `gamescope -- ...`.
- Lessons brought forward into the README from v2.x debugging:
  - Steam Input intercepts gamepads system-wide whenever the Steam client is running; quit Steam before launching to avoid duplicate input devices.
  - 8BitDo Ultimate must be physically in X-input mode for clean XInput; `SDL_JOYSTICK_HIDAPI=0` is **not** set in the wrapper because it broke joystick axes when Steam Input was off.
  - In-game settings: keep "Windowed Fullscreen" (FullscreenMode=1); switching to Exclusive Fullscreen (mode 0) inside gamescope causes UE to fall back to 1368×768 and blank-screen.
  - KDE fractional scaling on the portrait monitor causes gamescope to render at logical 1440×2560 instead of physical 4K. Disable scaling on DP-2 or use the override env vars.
