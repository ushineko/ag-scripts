# Peripheral Battery Monitor
Version 1.3.2

A small, always-on-top, frameless window for Linux (optimized for KDE Wayland) that displays the battery levels of your Logitech and Keychron peripherals, plus optional Claude Code API usage tracking.

![Peripheral Battery Monitor](assets/screenshot.png)

## Table of Contents
- [Features](#features)
- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [Manual Usage](#manual-usage)
- [Calibrating Claude Code Usage Tracking](#calibrating-claude-code-usage-tracking)
- [Logging](#logging)
- [Changelog](#changelog)

## Features
- **Logitech Support**: Uses `solaar` libraries to fetch precise mouse battery levels.
- **Keychron Support**:
  - **Bluetooth**: Uses `upower` to fetch battery levels %.
  - **Wired**: Detects USB connection and shows "Wired" status.
  - **Wireless (2.4G)**: Detects 2.4G receiver connection and shows "Wireless" status (battery level unavailable over 2.4G).
- **Arctis Headsets**: Uses `headsetcontrol` to fetch battery levels.
- **AirPods Support**: Advanced BLE scanning to fetch granular battery levels for Left, Right, and Case. Supports disconnected monitoring. Now with fallback logic and Case display!
- **Claude Code Integration**: Displays token usage within rolling time windows (1h-12h) with progress bar and countdown to reset. Auto-hides if Claude Code is not installed. Configurable session budget, window duration, and reset hour via right-click menu.
  - **Note**: Tracks local CLI usage only (from `~/.claude/projects/`). Does not include usage from claude.ai web interface or other devices. Best suited for single-system workflows where most usage is via Claude Code CLI.
- **Wayland Compatible**: Uses system-native movement for dragging.
- **KDE Plasma Integration**: Automatically installs KWin window rules for "Always on Top" and "No Titlebar".
- **Auto-Remember**: KWin remembers the window position and screen between sessions.
- **Compact UI**: Clean, dark-mode 2x2 grid dashboard showing all 4 devices.

## Requirements
- Python 3.12+ (tested on 3.14)
- `PyQt6` 
- `solaar`
- `upower` (for Bluetooth keyboards)
- `headsetcontrol` (for Arctis headsets)
- `bluez` (bluetoothctl)
- `python-bleak` (for AirPods BLE scanning)
- `python-structlog` (for structured logging)

## Quick Start
1. Ensure your Logitech mouse is connected (Unifying/Bolt receiver) and Keychron keyboard is paired via **Bluetooth**.
2. Run the installer:
   ```bash
   ./install.sh
   ```
3. Launch via your applications menu: **Peripheral Battery Monitor**

## Manual Usage
```bash
python3 peripheral-battery.py
# Or for troubleshooting:
python3 peripheral-battery.py --debug
```

## Calibrating Claude Code Usage Tracking

The Claude Code section tracks local CLI token usage against a configurable budget. Since Claude's actual rate limits aren't exposed via API, you'll need to calibrate the settings to match your plan.

### Step 1: Find Your Reset Time

In Claude Code, run `/usage` and note the reset time displayed (e.g., "Resets 2:00am"). This is your **Reset Hour**.

Right-click the monitor → **Claude Code** → **Reset Hour** → Select the matching hour (e.g., "2am").

### Step 2: Determine Your Window Duration

Claude uses rolling time windows. The `/usage` command shows a countdown to reset. If it says "Resets in 4h 30m" and you know the reset hour is 2am, you can calculate your window duration.

Common values:
- **Max plan**: Often 4-5 hour windows
- **Pro plan**: May vary

Right-click → **Claude Code** → **Window Duration** → Select your window (1h-12h options available).

### Step 3: Calibrate Your Budget

1. Note your current usage percentage from `/usage` (e.g., "50%")
2. Set a test budget in the monitor (e.g., 20k tokens)
3. Compare the monitor's percentage to `/usage`
4. Adjust the budget until they roughly match

**Example calibration:**
- `/usage` shows 50%
- Monitor shows 49% with 20k budget
- ✓ Budget is calibrated correctly

### Troubleshooting

| Symptom | Solution |
|---------|----------|
| Monitor shows much lower % than /usage | Decrease the budget (try 15k, 10k) |
| Monitor shows much higher % than /usage | Increase the budget (try 25k, 50k) |
| Countdown timer doesn't match | Adjust the reset hour and/or window duration |
| Usage resets mid-window | Your window duration doesn't match Claude's actual windows |

### Limitations

- Only tracks local CLI usage from `~/.claude/projects/`
- Does not include claude.ai web interface or other devices
- Best suited for single-system workflows

## Logging
Logs are automatically saved in JSON format for debugging:
- **Location**: `~/.local/state/peripheral-battery-monitor/peripheral_battery.log`
- **Rotation**: Keeps 1 backup file (Max 5MB).

## Changelog

### v1.3.2
- Expanded reset hour menu to show all 24 hours (previously only showed every 2 hours)

### v1.3.1
- Fixed bug where Claude Code section would permanently hide when no activity data was available in the current session window
- Section now shows "No activity" state instead of hiding when there's no data

### v1.3.0
- Added Claude Code usage stats section below the battery grid
- Window-based token counting (matches Claude's 4-hour session windows for Max plans)
- Shows token usage with progress bar (color-coded: green/yellow/red by percentage)
- Displays countdown to window reset and API call count
- Auto-hides if Claude Code is not installed
- Configurable session budget via right-click menu (10k-1M, Unlimited)
- Configurable window duration via right-click menu (1h-12h)
- Configurable reset hour to align with Claude's actual session windows (from `/usage`)
- Toggle visibility via right-click menu

### v1.2.4
- Keychron: Bluetooth battery now prioritized over "Wired" status when keyboard is charging via USB but connected via BT

### v1.2.3
- Added screenshot to README

### v1.2.2
- Added faulthandler import for debugging
- Refactored data fetching via subprocess

### v1.2.1
- Relaxed BLE RSSI threshold to -85
- 30-second battery status refresh interval
- Prevented worker thread overlap

### v1.2.0
- Added AirPods BLE scanning with L/R/Case status
- Added fallback logic for disconnected device monitoring
- Added unit tests for battery logic

### v1.1.1
- Single instance enforcement via QLockFile
- Dynamic battery status icons in UI
- Fixed mouse device resource exhaustion (dbus/systemd cache)

### v1.1.0
- Added Arctis headset support via headsetcontrol
- Added structured logging with structlog

### v1.0.1
- Enhanced Keychron support for Wired/Bluetooth/2.4G connections

### v1.0.0
- Initial release
- Logitech mouse support via solaar
- Keychron keyboard support (Bluetooth)
- KDE Wayland integration with KWin rules
