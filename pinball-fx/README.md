# Pinball FX Gamescope Wrapper

A small wrapper that adds [gamescope](https://github.com/ValveSoftware/gamescope) (with portrait-monitor pinning) to Heroic-launched Pinball FX. Heroic continues to handle Wine selection, Epic Online Services authentication (so DLC / Pinball Pass content works), and the menu entry. We just wrap the launch.

HDR support was dropped in v3.1.0 — see the changelog for the wine/Proton/Steam-Input tradeoff that forced the choice.

**Version**: 3.1.4

## Table of Contents

- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Heroic Per-Game Setup](#heroic-per-game-setup)
- [Env Overrides](#env-overrides)
- [Caveats Discovered During v2.x Debugging](#caveats-discovered-during-v2x-debugging)
- [Uninstallation](#uninstallation)
- [Files](#files)
- [Testing](#testing)
- [Changelog](#changelog)

## Architecture

```
Heroic GUI ─launch─▶ pinball_fx_wrapper.sh ─exec─▶ gamescope … -- wine PinballFX.exe <epic-auth args>
                            │
                            ├─▶ detect_portrait_screen.py     (logical W H X Y)
                            └─▶ install_kwin_rule.py          (pin gamescope wmclass to portrait)
```

Heroic invokes `pinball_fx_wrapper.sh` as its per-game "Wrapper Command". Heroic appends the wine command, the game .exe, and the Epic Online Services auth args. The wrapper:

1. Detects the portrait monitor's logical geometry via PyQt6.
2. Refreshes the KWin rule pinning `wmclass=gamescope` to that geometry (force-fullscreen, no border).
3. `exec`s `gamescope -W <w> -H <h> -w <w> -h <h> -f -- <args from Heroic>`.

Why this architecture (instead of v2's standalone Python launcher): the v2 launcher couldn't mint Epic Online Services auth tokens, so DLC / Pinball Pass content was invisible to the game. Rather than reimplement Epic OAuth, we hand the launch flow back to Heroic and only wrap the parts Heroic doesn't do (gamescope, monitor placement).

## Requirements

- KDE Plasma on Wayland
- `gamescope` 3.16+
- Heroic Games Launcher with Pinball FX installed via the Epic backend
- System wine (e.g. `wine` 11.x). **Not Proton** — see the changelog for v3.1.0 for why
- Python 3.11+ with PyQt6 (for screen detection)
- Bash

## Installation

```bash
./install.sh
```

The installer:

- chmods the wrapper + helper executable.
- Removes any v1.x `PinballFixer.desktop` and v2.x `PinballFX.desktop` entries.
- Removes any leftover Pinball FX KWin rule (current and legacy).
- Prints the per-game Heroic GUI configuration steps.

The installer does **not** create a desktop entry — Heroic's own "Pinball FX" menu entry becomes the canonical launcher in v3.

## Heroic Per-Game Setup

Open Heroic → Pinball FX → Settings:

1. **Wine version** → "Wine Default" (or any system wine). **Not Proton** — Proton's `winebus.sys` can't disambiguate when the Steam Input virtual gamepad is also present, breaking controller input.
2. **Wrapper Command** (Advanced / Other section) → exactly:

   ```
   /home/nverenin/git/ag-scripts/pinball-fx/pinball_fx_wrapper.sh
   ```

3. Save. Launch Pinball FX from Heroic's library or its menu entry.

That's it. Heroic mints fresh Epic auth tokens, runs system wine, and invokes our wrapper. The wrapper adds gamescope + KWin pinning.

## Env Overrides

Set these in Heroic's per-game "Environment Variables" section, or export them in your shell when launching from a terminal:

| Var | Default | Effect |
| --- | ------- | ------ |
| `PINBALL_FX_WIDTH` | detected logical width | Sets gamescope's `-w` (nested width) — the resolution the GAME thinks its display is. Use `2160` to make UE offer 4K in the in-game resolution menu. |
| `PINBALL_FX_HEIGHT` | detected logical height | Sets gamescope's `-h` (nested height). Pair with `PINBALL_FX_WIDTH=2160 PINBALL_FX_HEIGHT=3840` for 4K. |

## Caveats Discovered During v2.x Debugging

These caused real-world failures while iterating on the launcher; documenting so you don't rediscover them.

### The wine vs Proton + Steam Input vs HDR tradeoff (resolved in v3.1.0)

The bisect that drove v3.1.0:

| Combo | HDR | Controller |
| --- | --- | --- |
| System wine + wrapper | ❌ (`--hdr-enabled` doesn't propagate cleanly through wine 11.x's DXVK + gamescope WSI) | ✅ always |
| Proton-GE + wrapper, Steam off | ✅ | ✅ |
| Proton-GE + wrapper, Steam on | ✅ | ❌ — buttons registered but no in-game action |

The Proton-GE failure: when the Steam **client** is running (even just in the background — `steam-runtime-launcher-service --alongside-steam` stays alive after closing the window), Steam Input creates a virtual `Microsoft X-Box 360 pad` (vendor `0x28de`) alongside every real gamepad. Proton-GE's `winebus.sys` enumerates both via udev (not SDL2 — `SDL_JOYSTICK_BLACKLIST_DEVICES` does nothing here, attempted in v3.0.1) and its XInput layer can't disambiguate. System wine's gamepad path handles the duplicate gracefully.

v3.1.0 picked controller over HDR: dropped `--hdr-enabled` and the HDR env vars from the wrapper, switched the recommended Heroic Wine version from GE-Proton back to system wine. Pinball FX renders in SDR; controller works regardless of Steam.

If you want HDR back later, the bind-mount-over-`/dev/input/eventX` approach (described in the changelog) is the path — but it adds a `unshare -m -r` step to the wrapper and depends on the runtime device-number lookup. Not worth it for a pinball game in this user's view.

### 8BitDo Ultimate Wireless mode

Set the controller physically to **X-input mode** (the dongle's mode switch — exact button combo varies by dongle revision). In X-input mode it appears as "8BitDo Ultimate Wireless / Pro 2 Wired Controller" and Pinball FX's XInput layer maps it correctly.

### In-game settings: pick "Borderless Windowed"

In Pinball FX → Settings → Display → Window Mode, pick **"Borderless Windowed"**. This is what UE labels `FullscreenMode=1` in `<wine-prefix>/drive_c/users/<user>/AppData/Local/PinballFX/Saved/Config/WindowsNoEditor/GameUserSettings.ini`.

- **"Borderless Windowed"** (`FullscreenMode=1`): fills gamescope's nested surface correctly on the portrait monitor.
- **"Windowed"** (default in some game states): renders into a sub-region of the gamescope surface that's sized as if the display were landscape, leaving the rest of the portrait monitor empty.
- **"Fullscreen"** (`FullscreenMode=0`, exclusive): UE can't enumerate display modes inside gamescope's nested compositor and falls back to its default 1368×768 — blank screen on launch.

If you accidentally toggle to Fullscreen and lose the display, the game keeps a `.bak` of the previous config in the same directory. Restore it: `cp GameUserSettings.ini.bak GameUserSettings.ini`.

### KDE fractional scaling and gamescope render resolution

If your portrait monitor uses fractional scaling (e.g. 1.5× on a 4K portrait), PyQt6 reports logical 1440×2560 instead of physical 2160×3840. Gamescope renders at logical 1440×2560 by default and KWin upscales to physical (slightly soft).

Two ways to get sharper output:

- Disable KDE scaling on the portrait monitor (System Settings → Display → DP-X → Scale: 100%). Then logical = physical. Pixel-perfect.
- Or set `PINBALL_FX_WIDTH=2160 PINBALL_FX_HEIGHT=3840` env. Gamescope renders at 4K, downscales to the logical 1440×2560 buffer, KWin upscales back. Better than pure 1440×2560 but still has the KWin step.

### Steam Input persistent toggle (alternative to keeping Steam off)

v3.1.0 makes the controller work whether Steam is running or not by switching to system wine, so this is no longer required. Keeping the note for context: with Proton-GE, you'd need either to fully exit Steam before launching, or persistently disable Steam Input for the 8BitDo via Steam → Settings → Controller (per-controller toggle).

## Uninstallation

```bash
./uninstall.sh
```

Removes legacy v1.x / v2.x desktop entries, removes the KWin rule, refreshes desktop caches. Reminds you to manually clear the Wrapper Command and reset the Wine version in Heroic's per-game settings.

## Files

| File | Purpose |
| ---- | ------- |
| `pinball_fx_wrapper.sh` | The wrapper Heroic invokes. ~50 lines of bash. |
| `detect_portrait_screen.py` | Prints `<W> <H> <X> <Y>` (logical) for the single portrait monitor; exits non-zero if not exactly one. |
| `install_kwin_rule.py` | Installs/uninstalls the `wmclass=gamescope` KWin placement rule. Reused unchanged from v2.x. |
| `install.sh` / `uninstall.sh` | Installer / uninstaller (no .desktop entries — Heroic owns the menu entry). |
| `tests/test_install_kwin_rule.py` | pytest coverage for the KWin rule install/uninstall logic. |
| `specs/` | Spec history (001–004). |
| `validation-reports/` | Validation report per release. |

## Testing

```bash
python3 -m pytest tests/ -v
```

Tests cover KWin rule install / uninstall (including legacy v1.x rule migration). The wrapper script (bash) and the screen-detect helper (PyQt6) are smoke-tested manually because they're thin glue around `gamescope` and Qt.

## Changelog

### v3.1.4

- **Fixed v3.1.3's "stuck on playing" still happening** in real launches. Two bugs:
  - Reaper pkill pattern matched `PinballFX-Win64-Shipping.exe` but the `gamescopereaper` cmdline references the LAUNCHER exe (`PinballFX.exe`), not the running shipping process. Reaper survived. v3.1.4 splits the pattern: `GAME_PATTERN` for the watchdog (matches the running shipping exe), `LAUNCHER_PATTERN` for the reaper kill (matches `PinballFX.exe`).
  - `wineserver -k` is a no-op when no wineserver is running — which is exactly the post-game-exit state. Orphan `winedevice.exe` daemons survived. Cleanup now also SIGKILLs any wine system daemon (`winedevice` / `services.exe` / `plugplay.exe` / `explorer.exe` / `wineserver`) whose `/proc/PID/environ` shows `WINEPREFIX` matching ours. Scoped so other wine apps with a different prefix are untouched.

### v3.1.3

- **Fixed Heroic still stuck on "playing" after wrapper exit**: even with v3.1.2's watchdog killing gamescope cleanly, Heroic kept reporting "playing" because it polls for any process owning the game's `WINEPREFIX`, and wine system daemons (`winedevice.exe` etc.) linger after the game closes. Cleanup trap now runs `wineserver -k` for the inherited `WINEPREFIX`, which signals wineserver to terminate all its children. Daemons die promptly; Heroic drops "playing" within seconds.

### v3.1.2

- **Fixed Heroic stuck on "playing" after game exit**: the v3.1.1 EXIT trap was correct but never fired in practice. `gamescopereaper` is a subreaper waiting for ALL descendants to exit, including wine's `winedevice.exe` daemons which can linger for minutes after the game closes. Wrapper's `wait $GS_PID` blocked on that, trap never ran, Heroic kept reporting "playing".
- v3.1.2 adds a background watchdog: it waits for `PinballFX-Win64-Shipping.exe` to appear (up to 120s for cold-prefix shader compile), then watches for its disappearance, then SIGTERMs gamescope (3s grace) and SIGKILLs leftover `gamescopereaper` matching the game's cmdline. Heroic now drops "playing" within seconds of the in-game quit.

### v3.1.1

- **Fixed `-W -H` vs `-w -h` semantics**: in v3.1.0 the wrapper passed `-W $PINBALL_FX_WIDTH -H $PINBALL_FX_HEIGHT -w $LW -h $LH`, which made the OUTPUT buffer 4K but left the GAME seeing the logical screen size (1440×2560 max). UE's in-game resolution menu maxed at 1440 and fell back to its saved 1368×768. v3.1.1 swaps the semantics so `PINBALL_FX_WIDTH/HEIGHT` controls the NESTED width/height (`-w -h`) — what the game thinks its display is. Output buffer (`-W -H`) is always the logical screen.
- **Cleanup orphaned `gamescopereaper` on exit**: gamescope's reaper child sometimes survives parent death and keeps Heroic stuck in 'playing' state until manually killed. Wrapper now traps `EXIT INT TERM` and sweeps `gamescopereaper.*PinballFX\.exe` before returning. Wrapper no longer `exec`s gamescope (needs to outlive it to fire the trap).
- README env-overrides table updated to describe the new semantics.

### v3.1.0 (breaking — feature removed)

- **Dropped HDR support entirely.** Bisect locked the cause of the v3.0.x controller failure to Proton-GE specifically: when Steam is running, Proton-GE's `winebus.sys` can't disambiguate between the real 8BitDo and Steam Input's virtual XInput pad, leaving controller buttons no-op. System wine handles the duplicate gracefully but doesn't carry HDR through gamescope's WSI layer cleanly. Picking controller over HDR.
- Wrapper no longer sets `ENABLE_GAMESCOPE_WSI=1` / `DXVK_HDR=1` and no longer passes `--hdr-enabled` to gamescope. The `PINBALL_FX_NO_HDR` env override is removed (no-op now).
- README's recommended Heroic Wine version is now "Wine Default" (system wine) instead of GE-Proton.
- Migration: in Heroic → Pinball FX → Settings → Wine version, switch back to system wine. Wrapper Command stays unchanged. Heroic prefix at `~/Games/Heroic/Prefixes/proton/Pinball FX` (Proton-bootstrapped) can be deleted; the original wine prefix at `~/Games/Heroic/Prefixes/default/Pinball FX` is back in use.

### v3.0.2

- Removed the v3.0.1 `SDL_JOYSTICK_BLACKLIST_DEVICES` env. Bisect proved it didn't fix the Steam Input gamepad conflict — Proton's `winebus.sys` enumerates joysticks via udev, not SDL2, so SDL hints never reach the layer that picks the device.
- README rewritten with the actual root cause and the two real workarounds (fully exit Steam, or disable Steam Input per-controller in Steam Settings).
- Wrapper comment now documents the gotcha so future readers don't waste time re-trying the SDL hint approach.

### v3.0.1

- Added `SDL_JOYSTICK_BLACKLIST_DEVICES=0x28de/0x11ff` to the wrapper env. **Did not work** — see v3.0.2 notes. Kept here for changelog continuity.

### v3.0.0 (breaking)

- **Re-architected** to use Heroic as the launcher with this tool as a gamescope wrapper. The standalone Python launcher (`pinball_fx_launch.py`), our own `PinballFX.desktop` menu entry, and the Heroic-config-parsing / Proton-autodetect / runner-resolution code are all removed.
- **Why**: the v2 standalone launcher couldn't mint Epic Online Services auth tokens, so DLC / Pinball Pass content was invisible. Heroic mints those tokens natively.
- New files: `pinball_fx_wrapper.sh` (~50-line bash wrapper Heroic invokes), `detect_portrait_screen.py` (small PyQt6 helper).
- Retained: `install_kwin_rule.py` and its tests.
- Documented caveats from v2.x debugging: Steam Input gamepad conflicts, 8BitDo X-input mode, in-game Exclusive Fullscreen blank-screen, and KDE fractional scaling resolution loss.

### v2.2.1

- Set `SDL_JOYSTICK_HIDAPI=0` to fix scrambled 8BitDo controller inputs. (Removed in v3 — turned out to break joystick axes once Steam Input was no longer involved.)

### v2.2.0

- Added Proton runner backend via `umu-run` with auto-detection (GE-Proton → proton-cachyos-slr → Proton-Experimental).

### v2.1.0

- Added `--hdr` / `--no-hdr` flags. Sets `--hdr-enabled` on gamescope and `ENABLE_GAMESCOPE_WSI=1` so DXVK presents through gamescope's WSI layer.

### v2.0.0 (breaking)

- **Replaced** the v1.x post-launch window fixer with a Python launcher that wrapped Pinball FX in gamescope.
- KWin rule pins gamescope's outer window (one stable client) instead of chasing the Pinball FX window.

### v1.0.0

- Initial release: post-launch window fixer with interactive monitor selection menu and persistent KWin rules.
