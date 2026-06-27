# Claude Usage Widget

A floating desktop widget that displays Claude Code API usage metrics via the Anthropic OAuth API. Runs on **macOS** (menu-bar agent `.app`) and **Windows** (run-from-source / `install.bat`).

> The directory is named `claude-usage-widget-windows` for historical reasons; the project is now cross-platform. Renaming the directory is deferred to avoid breaking paths/history.

## Table of Contents

- [Features](#features)
- [Platform Support](#platform-support)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Development](#development)
- [Changelog](#changelog)

## Features

- Always-on-top floating widget with 5-hour utilization progress bar
- Countdown timer to next usage window reset
- 7-day utilization display
- System tray / menu-bar icon with color-coded usage status
- Reads authoritative usage data from the Anthropic OAuth API (no local file parsing)
- Credentials read from the platform store: macOS **login Keychain**, Windows/Linux `~/.claude/.credentials.json`
- Automatic OAuth token refresh with exponential backoff (refreshed tokens written back to the store)
- Draggable widget with position persistence
- Selectable font size (right-click → Font Size; persisted)
- Right-click context menu (Refresh Now, Font Size, Minimize to Tray, Exit)
- Minimize to tray / restore from tray via left-click
- Single-instance enforcement
- Terminal modes for tmux/herd helper panes: live self-refreshing `--tui` line and one-shot `--line` (Qt-free, no PySide6 required)
- Structured logging with `--debug` and `--no-gui` modes

## Platform Support

| Platform | Distribution | Autostart | Credentials | Config / Logs |
|----------|--------------|-----------|-------------|---------------|
| **macOS** | PyInstaller `.app` (menu-bar agent, `LSUIElement`) installed to `/Applications` | LaunchAgent (`~/Library/LaunchAgents`) | login Keychain (`Claude Code-credentials`) | `~/Library/Application Support/claude-usage-widget` / `~/Library/Logs/claude-usage-widget` |
| **Windows** | Run-from-source / `install.bat` | Startup-folder shortcut | `~/.claude/.credentials.json` | `%APPDATA%` / `%LOCALAPPDATA%` |
| **Linux** | Run-from-source (`python -m src.main`) | — | `~/.claude/.credentials.json` | `~/.claude-usage-widget` |

## Requirements

- **macOS**: macOS 11+, a **framework** Python 3 build (the system `/usr/bin/python3` qualifies); `pip3 install -r requirements.txt -r requirements-dev.txt` for building
- **Windows**: Windows 10/11, Python 3.10+
- Claude Code CLI installed and logged in (`claude login`)

## Installation

### macOS

```bash
cd claude-usage-widget-windows
pip3 install --user -r requirements.txt -r requirements-dev.txt
./install.sh          # builds the .app, installs to /Applications, registers a LaunchAgent
```

First launch (unsigned app): if Gatekeeper blocks it, right-click the app in Finder → **Open** → confirm (once). The gauge icon appears in the menu bar; left-click it to show the widget. macOS may also prompt once to allow access to the `Claude Code-credentials` Keychain item — choose **Always Allow**.

To remove: `./uninstall.sh` (unloads the LaunchAgent, deletes the `.app`, and prompts before removing config + logs).

### Windows

```powershell
cd claude-usage-widget-windows
pip install -r requirements.txt
python -m src.main
```

Or run `install.bat` for guided setup with optional startup shortcut.

## Usage

### GUI Mode (default)

```powershell
python -m src.main           # Normal mode
python -m src.main --debug   # With debug logging
```

- **Right-click** the widget for context menu
- **Drag** the widget to reposition (position is saved)
- **Minimize button** (─) hides to system tray
- **Left-click tray icon** to show/hide widget

### Console Mode

```powershell
python -m src.main --no-gui          # Fetch and print usage
python -m src.main --no-gui --debug  # With verbose logging
```

### Terminal (TUI) Mode

For a small helper pane in a terminal multiplexer (tmux, herd, etc.). Both modes
are Qt-free — they do not import PySide6 — so they run in a minimal/headless
pane. Rendering uses [`rich`](https://github.com/Textualize/rich). Logs are kept
off the terminal (they would interleave with the redrawn line); pass
`--log-file PATH` to capture them. Status (offline, rate-limited, stale) is shown
inline.

```bash
python -m src.main --tui                 # live, self-refreshing dashboard (Ctrl-C to exit)
python -m src.main --tui --interval 15   # poll every 15s instead of the config default
python -m src.main --line                # print one compact line and exit
python -m src.main --line --no-color     # plain text (no ANSI)
```

**`--tui`** — a `rich.live.Live` display on the alternate screen (the pane is
cleared on entry and restored on exit). It fills the pane width: a 5-hour
progress bar that stretches to fill, the stats trailing it, and the reset
countdown floated to the far right (color-coded by 5-hour utilization):

```
Claude  5h ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  47%  ·  7d 31%  ·  sonnet 12%        resets 2h 15m
```

**`--line`** — one compact line, then exit, for status bars / `watch` loops. It
is width-aware: in a narrow pane the lower-priority segments (model breakdown,
then reset, then 7d) are dropped so the 5-hour reading always shows.

```
Claude 5h 47% · 7d 31% · reset 2h 15m · sonnet 12%
```

Color is enabled automatically only on a TTY with `NO_COLOR` unset.

> The terminal modes need only `rich` and `structlog` (no PySide6). If you run
> them from a different interpreter than the GUI (e.g. a system `python3` in a
> tmux pane), install those there: `python3 -m pip install --user rich structlog`.

**tmux** — run `--tui` in a dedicated pane, or call `--line` from the status bar:

```tmux
# dedicated helper pane:
split-window -v 'python -m src.main --tui'

# or in the status bar (re-runs on status-interval):
set -g status-right '#(cd /path/to/claude-usage-widget-windows && python -m src.main --line)'
```

### CLI Options

| Option | Description |
|--------|-------------|
| `--debug` | Enable verbose debug logging |
| `--no-gui` | Fetch usage from API and print a multi-line report to console, then exit |
| `--tui` | Run a compact, self-refreshing single-line terminal display (helper pane); Ctrl-C to exit |
| `--line` | Print one compact usage line to stdout and exit (for status bars / watch loops) |
| `--interval N` | Poll interval in seconds for `--tui` (default: config `update_interval_seconds`; minimum 5) |
| `--no-color` | Disable ANSI color in `--tui`/`--line` output |
| `--fetch-json` | Fetch usage and print it as JSON to stdout, then exit (used internally by the GUI's QProcess fetcher; logs go to stderr) |
| `--log-file PATH` | Write logs to file |

### Status Colors

| Color | 5-hour Utilization |
|-------|-------------------|
| Green | Below 50% |
| Yellow | 50-80% |
| Red | Above 80% |

## Configuration

Settings are stored in `config.json` under the platform config directory (macOS: `~/Library/Application Support/claude-usage-widget`; Windows: `%APPDATA%\claude-usage-widget`; Linux: `~/.claude-usage-widget`):

| Setting | Default | Description |
|---------|---------|-------------|
| `update_interval_seconds` | 60 | Base poll interval; auto-backs off on API rate limits (HTTP 429) |
| `opacity` | 0.95 | Widget transparency (0.0-1.0) |
| `widget_position` | null | Saved `[x, y]` position (auto bottom-right if null) |
| `font_size` | 9 | Base label font size in px (right-click → Font Size; title renders +2) |

## Architecture

```
src/
  main.py              # Entry point, QTimer, single-instance, --fetch-json child path
  fetcher.py           # QProcess-based async usage fetch (event loop, no threads)
  oauth.py             # OAuth credentials, token refresh, usage API, backoff
  tui.py               # Qt-free terminal rendering via rich (--tui full-width dashboard, --line one-shot)
  widget.py            # PySide6 floating widget (frameless, translucent)
  tray.py              # QSystemTrayIcon with context menu
  config.py            # Settings persistence
  logging_config.py    # structlog setup
```

Data flow: A single `QTimer` triggers an asynchronous fetch on the Qt event loop. The fetch runs in a short-lived child process (`UsageFetcher` spawns the app's own binary with `--fetch-json` via `QProcess`), which prints the usage JSON to stdout; the parent parses it on `QProcess.finished` and delivers it via Qt signal to both the widget and tray icon — no duplicate API calls and no worker threads. (Earlier versions used a `QThread`; destroying it before it fully terminated made Qt `abort()` the process, so the design moved to QProcess, matching the pattern used elsewhere in this repo.)

## Development

```powershell
pip install -r requirements-dev.txt
pytest tests/
```

## Changelog

### v3.1.0 (2026-06-27)

- Added terminal (TUI) modes for tmux/herd helper panes, both Qt-free (no PySide6 import on these paths):
  - `--tui`: a compact, self-refreshing single-line display that redraws in place on the poll interval; keeps the last-known-good reading (marked stale) on transient errors, backs off on HTTP 429, and exits cleanly on Ctrl-C
  - `--line`: prints one compact line and exits, for status bars / watch loops
- Width-aware rendering: lower-priority segments (model breakdown → reset → 7d) are dropped in narrow panes so the 5-hour reading always shows
- ANSI color matching the GUI thresholds, auto-enabled only on a TTY with `NO_COLOR` unset; `--no-color` to force off
- `--interval N` to override the `--tui` poll cadence (minimum 5s)
- Logs are kept off the terminal in `--tui`/`--line` (they previously went to stderr, which interleaved with the redrawn line); use `--log-file PATH` to capture them
- Rendering uses [`rich`](https://github.com/Textualize/rich) (new dependency): `--tui` runs a `rich.live.Live` display on the alternate screen, so the launching shell's command echo and prior pane content are cleared on entry and the pane is restored on exit; color/width detection is handled by the library
- `--tui` is a full-width dashboard: a 5-hour `rich` progress bar that stretches to fill the pane, the 5h/7d/model stats trailing it, and the reset countdown floated to the far right (`--line` stays the compact single line for status bars)
- New `src/tui.py`

### v3.0.2 (2026-06-23)

- macOS: widget now follows across Spaces and shows over fullscreen apps (sets NSWindow `collectionBehavior` = canJoinAllSpaces | fullScreenAuxiliary)
- Handle API rate limiting (HTTP 429) gracefully: the poll interval backs off exponentially — honoring the server's `Retry-After` — then resets on the next success
- Preserve last-known-good readings: on any transient error the widget keeps showing the last reading with a `(reason · age)` staleness note, and the tray keeps its colored icon (tooltip marked "stale") instead of going gray — only a cold start with no cached reading shows an error/"no data" state
- Raised the default poll interval from 30s to 60s to reduce rate-limit pressure

### v3.0.1 (2026-06-23)

- Fixed a crash (SIGABRT) after a few update cycles: the usage fetch ran in a `QThread` that Qt `abort()`ed when destroyed before it fully terminated
- Replaced the `QThread` worker with an event-loop `QProcess` fetcher (`src/fetcher.py`), matching the async pattern used elsewhere in the repo (vscode-launcher, vpn-toggle) — no worker threads
- Added an internal `--fetch-json` mode (JSON to stdout, logs to stderr) used by the QProcess fetcher

### v3.0.0 (2026-06-23)

- **macOS support**: PyInstaller `.app` bundle (menu-bar agent, `LSUIElement`), `install.sh`/`uninstall.sh`, LaunchAgent autostart, `scripts/build_macos.sh`, and a generated `.icns`
- macOS-native config (`~/Library/Application Support`) and log (`~/Library/Logs`) paths via a new `src/platform_support.py`
- macOS credentials read from the login **Keychain** (`Claude Code-credentials`); refreshed tokens written back to the Keychain
- Fixed startup crash on the macOS framework Python (3.9) caused by PEP 604 (`X | None`) annotations — added `from __future__ import annotations`
- Widget stays on top on macOS (NSPanel `hidesOnDeactivate = NO` + floating level, set natively)
- Selectable, persisted font size (right-click → Font Size); widget width scales with the font
- Cross-platform entry wrapper `app_main.py` for PyInstaller

### v2.0.0 (2026-03-04)

- Complete rewrite: replaced JSONL file parsing with Anthropic OAuth usage API
- Replaced CustomTkinter + pystray with PySide6 (QSystemTrayIcon, frameless QWidget)
- Eliminated calibration (API provides authoritative utilization percentages)
- Single QTimer + worker thread drives both widget and tray (no duplicate polling)
- Added minimize-to-tray / restore from tray
- Added single-instance enforcement via QLockFile
- Removed dead code: popup.py, calibration.py, claude_stats.py
- Simplified config: removed session_budget, window_hours, reset_hour, token_offset

### v0.1.0 (2025-02-02)

- Initial release with CustomTkinter floating widget and pystray system tray
