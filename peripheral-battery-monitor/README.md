# Peripheral Battery Monitor

A small, always-on-top, frameless window for Linux (optimized for KDE Wayland) that displays the battery levels of your Logitech and Keychron peripherals.

## Features
- **Logitech Support**: Uses `solaar` libraries to fetch precise mouse battery levels.
- **Keychron (Bluetooth) Support**: Uses `upower` to fetch paired keyboard battery levels.
- **Wayland Compatible**: Uses system-native movement for dragging.
- **KDE Plasma Integration**: Automatically installs KWin window rules for "Always on Top" and "No Titlebar".
- **Auto-Remember**: KWin remembers the window position and screen between sessions.
- **Compact UI**: Clean, dark-mode dashboard showing both devices.

## Requirements
- Python 3.12+ (tested on 3.14)
- `PyQt6` 
- `solaar`
- `upower` (for Bluetooth keyboards)

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
```
