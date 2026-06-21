# Spec 014: macOS .app Bundle for vscode-launcher

> **Note**: This work has no associated issue tracker ticket. Consider creating one for traceability.

**Status: COMPLETE**

## Problem

Spec 013 made vscode-launcher run on macOS but installed it as a CLI symlink
plus a LaunchAgent — there was no `.app` in `/Applications`, so the launcher
was not discoverable in Finder or Spotlight. Spec 013 listed `.app` packaging
as "out of scope", but that contradicted its own repeated direction to "follow
clockwork-orange's pattern": clockwork-orange ships a **PyInstaller `.app`
bundle** ([scripts/build_macos.sh](../../clockwork-orange/scripts/build_macos.sh),
`Clockwork Orange.spec`). This spec resolves that contradiction by packaging
vscode-launcher the same way and supersedes the "`.app` bundle packaging" line
in spec 013's Out-of-Scope list.

## Empirical findings (2026-06-21, macOS 26.5, M1 Max)

| # | Finding | Detail |
|---|---------|--------|
| 1 | System `python3` is a framework build | `/usr/bin/python3` 3.9.6 reports `PYTHONFRAMEWORK=Python3`, which PyInstaller requires for `.app` bundles — no Homebrew Python needed |
| 2 | clockwork-orange does not auto-copy to `/Applications` | It distributes via GitHub Releases (download → drag). For a from-source install we add the copy step ourselves |
| 3 | `iconutil` + `sips` present | `.icns` can be generated locally from the SVG |
| 4 | Frozen resource path differs | `Path(__file__).parent` points inside the archive when frozen; bundled data lives at `sys._MEIPASS` |

## What changed

### 1. Frozen-aware resource loading
`_resource_dir()` returns `sys._MEIPASS` when frozen, else the module dir.
`_resolve_app_icon()` uses it so the bundled SVGs resolve inside the `.app`.

### 2. App icon (`.icns`)
`scripts/create_icns.py` rasterizes the color `vscode-launcher.svg` (via
`QSvgRenderer`) at the iconset sizes (16–512 @1x/@2x) and runs `iconutil`.
Regenerated at build time; the `.icns` is a build artifact (gitignored).

### 3. PyInstaller spec (`vscode-launcher.spec`)
`--onedir --windowed` `BUNDLE` producing `dist/vscode-launcher.app`:
- `LSUIElement = true` → menu-bar agent, no Dock icon (still in
  `/Applications` + Spotlight).
- `bundle_identifier = com.vscode-launcher`, color `.icns`.
- Hidden imports `PyQt6.QtDBus` (KDE modules, inert on macOS) and
  `PyQt6.QtSvg` (SVG icon rendering).
- `tmux_lookup.py` is NOT bundled — it stays a PATH helper symlink.

### 4. Build script (`scripts/build_macos.sh`)
Checks PyInstaller/PyQt6 + framework build, regenerates the `.icns`, cleans,
runs PyInstaller against the spec, reports `dist/vscode-launcher.app`.

### 5. Install / uninstall
`install.sh` (macOS): builds the `.app` on demand if absent, copies it to
`/Applications` (falls back to `~/Applications` if not writable), symlinks
`vscode-launcher` → the installed app binary, and points the LaunchAgent at
that binary. `uninstall.sh` removes the `.app` from both Applications dirs and
stops the app-bundle process. The hook-removal awk now eats the trailing blank
line so repeated cycles don't accumulate blanks in `~/.zshrc`.

## Acceptance Criteria

- [x] `scripts/build_macos.sh` produces `dist/vscode-launcher.app` — built on system python3 3.9.6
- [x] The `.app` launches without crashing and degrades KDE-only features — frozen-binary smoke test ran the event loop cleanly
- [x] Bundled SVG icons resolve when frozen (`sys._MEIPASS`) — `_resolve_app_icon()` returns a non-null template `QIcon`
- [x] `.app` is a menu-bar agent (`LSUIElement`, no Dock icon) — confirmed in the installed bundle's `Info.plist`
- [x] App icon is a real `.icns` generated from the SVG — 1024px `ic12` icon, valid per `sips`
- [x] `install.sh` copies the `.app` into `/Applications` and points the LaunchAgent at it — verified live (pid running from the bundle binary)
- [x] The app is discoverable in Spotlight / Finder — `mdfind` returns `/Applications/vscode-launcher.app`
- [x] Relaunching from Spotlight/Finder surfaces the main window (v3.5.1) — macOS has no D-Bus to signal the running instance, so the app shows its window on activation; verified the handler fires on `open -a` against a hidden running daemon
- [x] `uninstall.sh` removes the `.app` and stops the bundle process — verified live; `/Applications` entry and process gone
- [x] Repeated install/uninstall leaves `~/.zshrc` byte-identical to pristine — verified via round-trip diff
- [x] Build artifacts (`build/`, `dist/`, `.icns`) are gitignored; the `.spec` is committed
- [x] README documents the macOS `.app` build + install
- [x] Linux behavior unchanged — install.sh Linux branch still symlinks the source script; full test suite green (168)

## Out of Scope

- Code signing / notarization (the `.app` is unsigned; Gatekeeper will warn on first open of a downloaded copy — a locally-built/installed copy runs fine)
- `.dmg` packaging and GitHub Releases distribution
- Windows packaging
- Homebrew cask

## Notes

- Build dependency: `pyinstaller` (`pip3 install --user pyinstaller`), build-time only.
- The menu-bar uses the monochrome template icon at runtime (spec 013); the
  `.icns` (color) is the Finder/Spotlight/app icon.
