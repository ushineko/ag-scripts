# Claude Usage Widget for Windows

A floating desktop widget that displays Claude Code API usage metrics via the Anthropic OAuth API.

## Table of Contents

- [Features](#features)
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
- System tray icon with color-coded usage status
- Reads authoritative usage data from the Anthropic OAuth API (no local file parsing)
- Automatic OAuth token refresh with exponential backoff
- Draggable widget with position persistence
- Right-click context menu (Refresh Now, Minimize to Tray, Exit)
- Minimize to tray / restore from tray via left-click
- Single-instance enforcement
- Structured logging with `--debug` and `--no-gui` modes

## Requirements

- Windows 10 or Windows 11
- Python 3.12+
- Claude Code CLI installed and logged in (`claude login`)

## Installation

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

### CLI Options

| Option | Description |
|--------|-------------|
| `--debug` | Enable verbose debug logging |
| `--no-gui` | Fetch usage from API and print to console |
| `--log-file PATH` | Write logs to file |

### Status Colors

| Color | 5-hour Utilization |
|-------|-------------------|
| Green | Below 50% |
| Yellow | 50-80% |
| Red | Above 80% |

## Configuration

Settings stored in `%APPDATA%\claude-usage-widget\config.json`:

| Setting | Default | Description |
|---------|---------|-------------|
| `update_interval_seconds` | 30 | How often to poll the API |
| `opacity` | 0.95 | Widget transparency (0.0-1.0) |
| `widget_position` | null | Saved `[x, y]` position (auto bottom-right if null) |

## Architecture

```
src/
  main.py              # Entry point, QTimer, worker thread, single-instance
  oauth.py             # OAuth credentials, token refresh, usage API, backoff
  widget.py            # PySide6 floating widget (frameless, translucent)
  tray.py              # QSystemTrayIcon with context menu
  config.py            # Settings persistence
  logging_config.py    # structlog setup
```

Data flow: A single `QTimer` triggers a worker `QThread` that calls the Anthropic OAuth usage API. The result is delivered via Qt signal to both the widget and tray icon — no duplicate API calls.

## Development

```powershell
pip install -r requirements-dev.txt
pytest tests/
```

## Changelog

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
