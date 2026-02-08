# Alacritty Maximizer (v2.0.0)

A simple tool to launch Alacritty either normally or maximized on a specific monitor, with optional auto-launch to a saved default.

## Table of Contents
- [Why?](#why)
- [Features](#features)
- [How it works](#how-it-works)
- [Auto-Launch (Default Monitor)](#auto-launch-default-monitor)
- [Installation](#installation)
- [Uninstallation](#uninstallation)
- [CLI Options](#cli-options)
- [Requirements](#requirements)
- [Files](#files)
- [Changelog](#changelog)

## Why?
Sometimes you want to open a terminal dedicated to a specific screen without dragging it there and valid window management rules are hard to generalize. This tool uses specific KWin rules to force the window to the correct screen and state.

## Features
- **Specific Monitor Launching**: Select which monitor to open Alacritty on.
- **Auto-Maximization**: Windows open fully maximized.
- **Borderless**: Windows open without titlebars for a clean look.
- **Robustness**: Uses screen coordinates to identify monitors, ensuring the "Left" monitor is always the "Left" monitor even if system indices change.
- **Movable**: Although maximized initially, windows can be moved or resized (e.g., using Taskbar r-click, or **Alt+LeftClick** drag in KWin).
- **Auto-Launch**: Save a default monitor and skip the GUI on subsequent launches.

## How it works
1.  **Selection**: You choose a monitor or "Normal Start" from the GUI.
2.  **KWin Interaction**:
    - The "Maximize on Monitor" option launches `alacritty` with a special window class: `--class alacritty-pos-X_Y,alacritty-pos-X_Y`.
    - Pre-installed KWin rules match this class and apply:
        - **Position**: Forces the window to the monitor's coordinates.
        - **Size**: Applies "Maximized" state initially.
        - **Decorations**: Removes window borders/titlebar.

## Auto-Launch (Default Monitor)

You can save a default monitor so the GUI is skipped on future launches:

1. Open the launcher GUI
2. Select a monitor
3. Check **"Save as default (auto-launch next time)"**
4. Click **Launch**

On subsequent launches, Alacritty will open directly on the saved monitor without showing the GUI.

To change or clear the default:
- Run with `--choose` to force the GUI and pick a new default
- Run with `--clear-default` to remove the saved default
- Use the **"Clear Default"** button in the GUI (visible when a default is set)

If the saved monitor is no longer connected, the GUI is shown automatically.

Config is stored at `~/.config/alacritty-maximizer/config.json`.

## Installation

1.  Run the install script:
    ```bash
    ./install.sh
    ```
    This will:
    - Update your `~/.config/kwinrulesrc` with the necessary rules.
    - Reload KWin.
    - Install a desktop entry `Alacritty Maximizer` to your applications menu.

## Uninstallation
To remove the tool and its rules:
```bash
./uninstall.sh
```

## CLI Options
```
python3 main.py [OPTIONS]

  --choose          Show monitor selection GUI even if a default is saved
  --clear-default   Clear the saved default monitor and exit
  --version         Show version and exit
```

## Requirements
- Linux with KDE Plasma (KWin)
- Python 3
- PyQt6 (`sudo pacman -S python-pyqt6` or `pip install PyQt6`)
- Alacritty

## Files
- `main.py`: The PyQt GUI launcher with auto-launch support.
- `config.py`: Configuration persistence (default monitor).
- `install_kwin_rules.py`: Script to inject KWin rules.
- `install.sh`: Master installation script.
- `uninstall.sh`: Removal script.

## Changelog

### v2.0.0
- Added saved default monitor config with auto-launch (skip GUI)
- Added `--choose` flag to force GUI when a default is set
- Added `--clear-default` flag to clear saved default from CLI
- Added "Save as default" checkbox and "Clear Default" button in GUI
- Config stored at `~/.config/alacritty-maximizer/config.json`
- Falls back to GUI if saved monitor is no longer connected
- Refactored launch logic into reusable `launch_alacritty()` function

### v1.1
- Switched to screen coordinates for monitor identification (robustness improvement)
- Monitor selection now resilient to system index changes

### v1.0
- Initial release
- PyQt6 GUI for monitor selection
- KWin rules for maximization and borderless windows
- Desktop entry installation
