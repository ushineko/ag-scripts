# Claude Usage Widget for Windows

A lightweight Windows system tray widget that displays Claude Code CLI usage metrics within rolling time windows.

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Calibration](#calibration)
- [Limitations](#limitations)
- [Development](#development)
- [Changelog](#changelog)

## Features

- System tray icon with color-coded usage status
- Real-time token consumption tracking
- Configurable session windows (1-12 hours)
- Snap-to-percentage calibration
- Lightweight (~5MB dependencies vs ~50MB for PyQt alternatives)

## Requirements

- Windows 10 or Windows 11
- Python 3.10+
- Claude Code CLI installed (`%USERPROFILE%\.claude\` directory must exist)

## Installation

```powershell
# Clone or download the repository
cd claude-usage-widget-windows

# Install dependencies
pip install -r requirements.txt

# Run
python src/main.py
```

## Usage

### GUI Mode (default)

```powershell
python -m src.main           # Normal mode
python -m src.main --debug   # With debug logging
```

1. Run the widget - it appears in the system tray
2. **Left-click** the tray icon to show/hide the detail popup
3. **Right-click** for the context menu (settings, calibration, exit)

### Console Mode (troubleshooting)

```powershell
python -m src.main --no-gui          # Scan and print stats, then exit
python -m src.main --no-gui --debug  # With verbose debug logging
```

Console mode is useful for:
- Verifying the widget can find and parse your Claude session files
- Debugging issues without starting the GUI
- Scripting/automation

### CLI Options

| Option | Description |
|--------|-------------|
| `--debug` | Enable verbose debug logging |
| `--no-gui` | Run in console mode (scan and exit) |
| `--log-file PATH` | Write logs to file (in addition to console) |

### Tray Icon Colors

| Color | Meaning |
|-------|---------|
| Green | Usage below 50% |
| Yellow | Usage between 50-80% |
| Red | Usage above 80% |

## Configuration

Settings are stored in `%APPDATA%\claude-usage-widget\config.json`:

| Setting | Default | Description |
|---------|---------|-------------|
| `session_budget` | 500000 | Token budget for the session window |
| `window_hours` | 4 | Duration of the rolling window |
| `reset_hour` | 2 | Hour when Claude's billing window resets |
| `token_offset` | 0 | Calibration adjustment |
| `update_interval_seconds` | 30 | How often to refresh data |

## Calibration

To sync with Claude's actual billing:

1. Run `/usage` in Claude CLI to see your current percentage
2. Right-click tray icon → **Calibrate...**
3. Enter the percentage from Claude
4. Choose adjustment mode:
   - **Adjust Budget**: Recalculates budget to match percentage
   - **Adjust Offset**: Adds token offset to match percentage

## Limitations

- Only tracks local CLI usage from `%USERPROFILE%\.claude\projects\`
- Does NOT include usage from claude.ai web interface
- Does NOT aggregate usage from other devices
- Manual calibration required (no automatic sync with billing API)

## Development

```powershell
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
pytest tests/

# Build standalone exe (optional)
pyinstaller --onefile --windowed src/main.py
```

## Changelog

### v0.1.0 (Unreleased)

- Initial implementation
- System tray integration with color-coded status
- Detail popup with token metrics
- Configurable session windows
- Snap-to-percentage calibration
- Structured logging with structlog
- `--debug` flag for verbose output
- `--no-gui` mode for console-only troubleshooting
- `--log-file` option for file logging
