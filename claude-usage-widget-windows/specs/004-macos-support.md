# macOS Support for Claude Usage Widget

> **Ticket**: No associated ticket — this is a personal public GitHub repo with no issue tracker (per project policy, specs are named without ticket IDs).

## Context

The Claude Usage Widget (currently v2.0.0) is a floating desktop widget that displays
Claude Code OAuth usage metrics (5-hour utilization, reset countdown, 7-day utilization)
in a frameless, always-on-top, draggable window with a color-coded system-tray icon. It
is built on **PySide6 (Qt6)** plus `structlog`, and is today packaged and documented as a
**Windows-only** project (`claude-usage-widget-windows`).

Research into two sibling projects shows a macOS port is low-risk because the widget's core
is already platform-agnostic:

- **Already cross-platform (no change needed):** the OAuth client (`src/oauth.py` reads
  `~/.claude/.credentials.json` via `USERPROFILE`/`expanduser` fallback, uses `urllib`),
  the display logic (`src/display.py`, pure Python), and all window features
  (`src/widget.py` uses Qt's `FramelessWindowHint` + `WindowStaysOnTopHint` +
  `WA_TranslucentBackground`, and `src/tray.py` uses `QSystemTrayIcon`, which Qt maps to
  the macOS menu bar automatically).
- **Windows-specific (must be replaced/added):** the installer/uninstaller (`install.bat`
  / `uninstall.bat`), the autostart mechanism (a Startup-folder `.lnk` shortcut created via
  PowerShell `WScript.Shell`), the `pythonw -m src.main` invocation, and the config/log
  path resolution which keys on `%APPDATA%`/`%LOCALAPPDATA%` (`src/config.py:get_config_dir`,
  `src/logging_config.py:get_log_dir`).

Reference implementations for the macOS patterns reused below:

- **`vscode-launcher`** (this repo): macOS `.app` bundle via PyInstaller with `LSUIElement`,
  a `~/Library/LaunchAgents/*.plist` LaunchAgent with an explicit `PATH` override,
  `$OSTYPE`-branching `install.sh`/`uninstall.sh`, `scripts/build_macos.sh`,
  `scripts/create_icns.py`, and a centralized `platform_support.py` (`IS_MACOS = sys.platform == "darwin"`).
- **`~/git/clockwork-orange`**: a `platform_utils.py` dispatcher module, a PyInstaller
  `.spec` with a `BUNDLE()` target and `.icns` icon, and `scripts/build_macos.sh` that
  **validates Python is a framework build** (a hard PyInstaller requirement for `.app`
  bundles).

**Decisions made up front (approved by maintainer):**

1. **Distribution:** PyInstaller `.app` bundle installed to `/Applications` (or
   `~/Applications` fallback), launched at login via a LaunchAgent. (Not run-from-source.)
2. **Paths:** macOS-native locations — config under `~/Library/Application Support/claude-usage-widget`,
   logs under `~/Library/Logs/claude-usage-widget`.

## Requirements

### R1 — Platform detection module
Add a small `src/platform_support.py` exposing `IS_WINDOWS`, `IS_MACOS`, `IS_LINUX`
boolean constants (`sys.platform == "darwin"`, etc.), mirroring `vscode-launcher`'s pattern.
All new platform branches route through these constants — no scattered `sys.platform` checks.

### R2 — macOS-native config and log paths
- `src/config.py:get_config_dir()`: on macOS return
  `~/Library/Application Support/claude-usage-widget`; keep existing Windows (`%APPDATA%`)
  and generic (`~/.claude-usage-widget`) behavior unchanged on their platforms.
- `src/logging_config.py:get_log_dir()`: on macOS return `~/Library/Logs/claude-usage-widget`;
  keep Windows (`%LOCALAPPDATA%`) and generic fallback unchanged.
- Directories are created if absent (preserve current `mkdir(parents=True, exist_ok=True)` behavior).
- OAuth credential path (`~/.claude/.credentials.json`) is already correct on macOS — no change.

### R3 — PyInstaller `.app` bundle
- Add a PyInstaller spec (e.g. `claude-usage-widget.spec`) with a `BUNDLE()` target producing
  `Claude Usage Widget.app`.
- `Info.plist` sets `LSUIElement = True` (menu-bar/tray agent, no Dock icon — the widget is a
  floating tray utility), `NSHighResolutionCapable = True`, and a `CFBundleIdentifier`
  (e.g. `com.nverenin.claude-usage-widget`).
- Bundle icon is a generated `.icns` (see R4). Hidden imports declared as needed
  (PySide6 plugins; `structlog`).
- Entry point is the existing `src/main.py` (`python -m src.main` equivalent).

### R4 — Icon asset (`.icns`)
- Provide a macOS `.icns` icon for the bundle. Generate it from an existing PNG/SVG source via
  `iconutil`/`sips` (a `scripts/create_icns.py` or shell helper, following
  `vscode-launcher/scripts/create_icns.py`). The dynamically generated **tray** icon
  (`src/tray.py`) is unchanged — this is only the Finder/Dock/bundle icon.

### R5 — Build script
- Add `scripts/build_macos.sh` that:
  - Verifies Python is a **framework build** (`sysconfig.get_config_var('PYTHONFRAMEWORK')`
    non-empty) and exits with a clear message if not (e.g. "use `/opt/homebrew/bin/python3` to
    create the venv"), matching `clockwork-orange`'s check.
  - Installs build deps (`pyinstaller` from `requirements-dev.txt`) and runs PyInstaller against
    the spec, producing `dist/Claude Usage Widget.app`.

### R6 — macOS installer (`install.sh`)
- Add an `install.sh` (or extend with `$OSTYPE` branching) that on macOS:
  - Builds the `.app` (via R5) if not already built.
  - Copies it to `/Applications`, falling back to `~/Applications` if `/Applications` is not writable.
  - Writes and loads a LaunchAgent (R7).
  - Prints clear "Installing… / Done" messages and post-install guidance (incl. first-launch
    Gatekeeper note for an unsigned app: right-click → Open).

### R7 — LaunchAgent autostart
- Generate `~/Library/LaunchAgents/com.nverenin.claude-usage-widget.plist` with:
  - `Label`, `ProgramArguments` pointing at the installed `.app` binary
    (`…/Claude Usage Widget.app/Contents/MacOS/<exe>`),
  - `RunAtLoad = true`, `KeepAlive = false`, `ProcessType = Interactive`.
- Load via `launchctl bootstrap "gui/$(id -u)" <plist>` (with a prior `bootout` to make
  re-install idempotent), mirroring `vscode-launcher/install.sh`.

### R8 — macOS uninstaller (`uninstall.sh`)
- Add/extend `uninstall.sh` to on macOS:
  - `launchctl bootout` and `rm -f` the LaunchAgent plist.
  - Remove the `.app` from `/Applications` and `~/Applications` (whichever exists).
  - Prompt before deleting config (`~/Library/Application Support/claude-usage-widget`) and
    logs (`~/Library/Logs/claude-usage-widget`).
  - Idempotent (`rm -f`, existence checks), with clear messages.

### R9 — Single-instance lock works on macOS
- Confirm the `QLockFile` single-instance guard (`src/main.py`) resolves a valid temp path on
  macOS and prevents a second instance when launched from both the LaunchAgent and a manual open.

### R10 — Documentation & versioning
- Rename/retitle docs so the README no longer presents the project as Windows-only: add a macOS
  Installation section, a Linux/macOS/Windows feature/support matrix, and macOS uninstall steps.
- Update the root repo `README.md` "Scripts/Projects" section to reflect macOS support.
- Bump version (source `src/__init__.py` **and** README) — propose **2.1.0** (additive macOS
  support); maintainer to approve the exact number during finalization.
- Note: the directory is named `claude-usage-widget-windows`; renaming the directory is **out of
  scope** for this spec (it would break paths/history) — call it out as a possible future cleanup.

### R11 — Tests
- Add unit tests for the platform-branching path helpers (R2): assert macOS returns the
  `~/Library/...` locations and Windows/generic branches are unchanged, using monkeypatched
  `sys.platform` / env vars (no real filesystem dependence on the host OS).
- Keep `src/display.py` / OAuth tests green (no behavior change expected).

## Acceptance Criteria

- [x] `src/platform_support.py` exists exposing `IS_WINDOWS`/`IS_MACOS`/`IS_LINUX`; new branches use it (R1)
- [x] `get_config_dir()` returns `~/Library/Application Support/claude-usage-widget` on macOS; Windows/generic unchanged (R2)
- [x] `get_log_dir()` returns `~/Library/Logs/claude-usage-widget` on macOS; Windows/generic unchanged (R2)
- [x] OAuth credentials resolve correctly on macOS (R2) — **deviation:** the spec assumed `~/.claude/.credentials.json` "needs no change", but Claude Code on macOS stores credentials in the **login Keychain** (`Claude Code-credentials`). `src/oauth.py` now reads/writes the Keychain via the `security` CLI on macOS and keeps the file path on Windows/Linux.
- [x] PyInstaller spec produces `Claude Usage Widget.app` with `LSUIElement=True` and a bundle identifier (R3)
- [x] A `.icns` bundle icon is generated and referenced by the spec (R4)
- [x] `scripts/build_macos.sh` validates framework Python and builds `dist/Claude Usage Widget.app` (R5)
- [x] `install.sh` builds + installs the `.app` to /Applications (or ~/Applications) on macOS (R6)
- [x] LaunchAgent plist is written to `~/Library/LaunchAgents/` and loaded via `launchctl`; widget starts at login (R7)
- [x] `uninstall.sh` removes the LaunchAgent, the `.app`, and (after prompt) config + logs; idempotent (R8)
- [x] Single-instance `QLockFile` lock works on macOS (`src/main.py` uses `QStandardPaths.TempLocation`; second launch logs `another_instance_running` and exits) (R9)
- [x] README updated: macOS install/uninstall sections + support matrix; root README updated (R10)
- [x] Version bumped consistently in `src/__init__.py` and README (3.0.0, maintainer-approved) (R10)
- [x] Unit tests cover the macOS path branches and pass; existing tests still pass (R11)
- [x] Validation report created in `validation-reports/` and committed alongside the changes

## Post-implementation deviations (discovered during macOS bring-up)

The spec assumed the widget's core was already macOS-ready. Debugging the built `.app` surfaced three issues fixed beyond the original requirements:

1. **Credentials are in the Keychain, not a file** (see amended R2 criterion above).
2. **PEP 604 crash on framework Python 3.9.** The macOS framework Python is 3.9.6; evaluated `X | None` annotations raised `TypeError` at import, so the `.app` crashed before drawing anything. Fixed by adding `from __future__ import annotations` to the `src/` modules.
3. **Widget didn't stay on top.** The `Qt.Tool` NSPanel hides when the background agent app loses focus. Fixed natively (ctypes → Obj-C runtime) by setting `hidesOnDeactivate = NO` and a floating window level in `FloatingWidget.showEvent`, gated on the `cocoa` QPA platform.

Also added a user-requested **selectable font size** (right-click → Font Size, persisted to config).

## Technical Notes

- **Framework Python is mandatory** for PyInstaller `.app` bundles. On Apple Silicon use
  `/opt/homebrew/bin/python3` to create the venv; the build script must fail loudly otherwise
  (this is the single most common macOS PyInstaller failure — see `clockwork-orange/scripts/build_macos.sh`).
- **Code signing / notarization are out of scope.** The `.app` is unsigned; document the
  first-launch Gatekeeper bypass (right-click → Open). Note this in the README.
- **No `PATH` override needed in the plist** (unlike `vscode-launcher`, which shells out to
  `code`). The widget is self-contained inside the bundle and shells out to nothing, so the
  minimal launchd `PATH` is fine. Do **not** copy that part of the vscode-launcher plist.
- **Tray icon already works on macOS** — `QSystemTrayIcon` renders in the menu bar. Watch only
  for Retina sizing of the generated pixmap in `src/tray.py:14–45`; verify it isn't blurry, but
  do not redesign it.
- **Default window position** (`src/widget.py:78–85`, bottom-right via primary-screen geometry)
  works on macOS but sits near the Dock; acceptable for v1 of the port. The widget is draggable
  and position-persistent, so a macOS-specific default is not required.
- **`requirements-dev.txt`** already lists `pyinstaller` (used by the Windows build path); reuse it.
- **Reversibility:** the entire feature is additive (new files + platform branches guarded by
  `IS_MACOS`). Rollback = revert the commit; on a user's machine, run `uninstall.sh`. No Windows
  behavior changes, so no risk to existing Windows users.
- **Reference files to crib from:**
  - `vscode-launcher/install.sh` (lines ~106–168: plist generation + `launchctl bootstrap`)
  - `vscode-launcher/uninstall.sh` (lines ~55–61: `bootout` + `rm`)
  - `vscode-launcher/vscode-launcher.spec` (Info.plist / `LSUIElement` BUNDLE)
  - `vscode-launcher/scripts/create_icns.py`
  - `clockwork-orange/scripts/build_macos.sh` (framework-build validation)
  - `clockwork-orange/Clockwork Orange.spec` (`BUNDLE()` target + `.icns`)

## Status: COMPLETE
