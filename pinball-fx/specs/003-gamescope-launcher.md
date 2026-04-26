# Spec 003: Gamescope Launcher

> **Note**: This work has no associated issue tracker ticket. ag-scripts is a personal monorepo with no tracker per project conventions.

**Status: COMPLETE**

## Description

Replace the post-launch KWin Window Fixer with a launcher that wraps Pinball FX in a [gamescope](https://github.com/ValveSoftware/gamescope) compositor. Gamescope contains the game in its own micro-compositor, so the chaotic resize/reposition behavior the prior tool worked around stops at gamescope's boundary. We pin gamescope's outer window — a single, well-behaved client — to the portrait monitor instead of chasing the game's window.

This is a breaking replacement: the old `configure_kwin.py` and its associated `Fix Pinball Window` desktop entry are removed.

## Requirements

- Launch path follows option (b): read `~/.config/heroic/GamesConfig/<id>.json` for `wineVersion.bin` and `winePrefix`, invoke gamescope wrapping wine directly. Heroic GUI is bypassed at launch time.
- Auto-detect the portrait monitor (the single connected output where height > width). A `--screen N` flag overrides detection.
- Spawn `gamescope` at the target monitor's native resolution with `-f` (fullscreen) and exec wine on the game `.exe`.
- A KWin rule pins gamescope's outer window (`wmclass=gamescope`) to the chosen monitor's geometry, force-fullscreen, no border. The rule is installed by the launcher idempotently on each run so monitor changes are picked up.
- Wine env carries esync / fsync / msync flags from the per-game Heroic config and `WINEDLLOVERRIDES` for DXVK so the prefix's installed DXVK actually loads.
- The desktop entry (`PinballFX.desktop`, Categories=Game) calls the new launcher.
- Uninstaller removes the desktop entry **and** the gamescope KWin rule.
- The old `configure_kwin.py`, `PinballFixer.desktop`, and the `Pinball FX Portrait Mode` KWin rule are removed.

## Acceptance Criteria

- [x] `pinball_fx_launch.py` exists, is executable, and reads the Heroic per-game JSON to derive wine binary + prefix.
- [x] Launcher detects the portrait monitor automatically when `--screen` is not supplied.
- [x] Launcher invokes gamescope with `-W`/`-H`/`-w`/`-h`/`-f` matching the chosen monitor and execs wine on `~/Games/Heroic/PinballFX/PinballFX.exe`.
- [x] Launcher installs a KWin rule for `wmclass=gamescope` pinning position+size to the chosen monitor's geometry, with `fullscreen=true (force)` and `noborder=true (force)`.
- [x] `install_kwin_rule.py --uninstall` removes the gamescope rule.
- [x] `PinballFX.desktop` invokes the launcher, lives under `Categories=Game;`.
- [x] `install.sh` installs the desktop entry and is idempotent.
- [x] `uninstall.sh` removes the desktop entry, removes the KWin rule, and is idempotent.
- [x] `configure_kwin.py` and `PinballFixer.desktop` are deleted from the repo.
- [x] Pytest suite under `tests/` covers: Heroic config parsing, portrait monitor detection (with mocked screens), gamescope command construction, and KWin rule install/uninstall against a tmp config path.
- [x] Old `Pinball FX Portrait Mode` rule, if present, is migrated out (uninstaller removes it on first run after upgrade).
- [x] README rewritten; version bumped to 2.0.0 in source + README.
- [x] Root README's pinball-fx entry updated.
- [x] Validation report in `validation-reports/` covers tests, lint, OWASP review, dependency scan, secrets check.

## Out of Scope

- Supporting Proton runners. The current Heroic config uses system wine; if `wineVersion.type` is anything other than `wine`, the launcher errors with a clear message rather than guessing a Proton invocation. Adding Proton/umu support is a future spec.
- Steam launches. This is a Heroic-Epic-only launcher.
- Heroic features that the GUI wires up (achievements, playtime tracking, cloud saves). Bypassing Heroic at launch time means we lose these. Acceptable for this game, which has none of them configured.

## Implementation Notes

- Heroic per-game config path: `~/.config/heroic/GamesConfig/56a31432931740cdb0112d237d7d65aa.json`. The app id is constant for this Epic title.
- DXVK is auto-installed by Heroic into the prefix; we set `WINEDLLOVERRIDES=dxgi,d3d11,d3d10core,d3d9=n,b` so wine prefers the prefix DLLs over its own.
- Gamescope on KDE Wayland runs nested. `--prefer-output` is a DRM-mode flag and is not used; we rely on the KWin rule for placement.
- KWin rule values: `2` = Force, `wmclassmatch=1` = exact match.
- Launcher exits non-zero when: Heroic config missing, wine binary missing, gamescope not on PATH, or no portrait monitor detected when `--screen` is omitted.
