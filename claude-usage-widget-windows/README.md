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

- Always-on-top floating widget with progress bar
- System tray icon with color-coded usage status
- Real-time token consumption tracking
- Right-click context menu on widget for quick settings access
- Configurable budget (100k-2M), window duration (30min-12h), reset hour (0-23)
- Snap-to-percentage calibration with live preview
- Structured logging with `--debug` and `--no-gui` modes
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

1. Run the widget - a floating widget appears on screen with progress bar
2. **Right-click** the widget for settings menu (Budget, Window Duration, Reset Hour, Calibrate, Exit)
3. **Drag** the widget to reposition it
4. System tray icon also available for redundant access to settings

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
2. Right-click the widget → **Calibrate...**
3. Use the slider or enter the percentage (1-200% supported)
4. Choose adjustment mode:
   - **Adjust Budget** (recommended): Recalculates budget to match percentage
   - **Adjust Token Count**: Adds token offset to match percentage
5. Preview shows the calculation before applying
6. Click **Apply** to save (confirmation shown before closing)

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

### v0.1.0 (2025-02-02)

- Initial release
- Always-on-top floating widget with progress bar and drag support
- System tray integration with color-coded status
- Right-click context menu on widget for all settings
- Configurable budget (100k-2M), window duration (30min-12h), reset hour (0-23)
- Calibration dialog with slider (1-200%), live preview, and confirmation feedback
- Escape key and X button close calibration dialog
- Structured logging with structlog
- `--debug` flag for verbose output
- `--no-gui` mode for console-only troubleshooting
- `--log-file` option for file logging
