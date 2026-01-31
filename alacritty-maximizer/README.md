# Alacritty Maximizer (v1.1)

A simple tool to launch Alacritty either normally or maximized on a specific monitor.

## Why?
Sometimes you want to open a terminal dedicated to a specific screen without dragging it there and valid window management rules are hard to generalize. This tool uses specific KWin rules to force the window to the correct screen and state.

## Version 1.1 Features
- **Specific Monitor Launching**: Select which monitor to open Alacritty on.
- **Auto-Maximization**: Windows open fully maximized.
- **Borderless**: Windows open without titlebars for a clean look.
- **Robustness**: Uses screen coordinates to identify monitors, ensuring the "Left" monitor is always the "Left" monitor even if system indices change.
- **Movable**: Although maximized initially, windows can be moved or resized (e.g., using Taskbar r-click, or **Alt+LeftClick** drag in KWin).

## How it works
1.  **Selection**: You choose a monitor or "Normal Start" from the GUI.
2.  **KWin Interaction**: 
    - The "Maximize on Monitor" option launches `alacritty` with a special window class: `--class alacritty-pos-X_Y,Alacritty`.
    - Pre-installed KWin rules match this class and apply:
        - **Position**: Forces the window to the monitor's coordinates.
        - **Size**: Applies "Maximized" state initially.
        - **Decorations**: Removes window borders/titlebar.

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

## Requirements
- Linux with KDE Plasma (KWin)
- Python 3
- PyQt6 (`sudo pacman -S python-pyqt6` or `pip install PyQt6`)
- Alacritty

## Files
- `main.py`: The PyQt GUI launcher.
- `install_kwin_rules.py`: Script to inject KWin rules.
- `install.sh`: Master installation script.
- `uninstall.sh`: Removal script.

## Changelog

### v1.1
- Switched to screen coordinates for monitor identification (robustness improvement)
- Monitor selection now resilient to system index changes

### v1.0
- Initial release
- PyQt6 GUI for monitor selection
- KWin rules for maximization and borderless windows
- Desktop entry installation
