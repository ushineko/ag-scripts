# Alacritty Maximizer

A simple tool to launch Alacritty either normally or maximized on a specific monitor.

## Why?
Sometimes you want to open a terminal dedicated to a specific screen without dragging it there and valid window management rules are hard to generalize. This tool uses specific KWin rules to force the window to the correct screen and state.

## How it works
1.  **Selection**: You choose a monitor or "Normal Start" from the GUI.
2.  **KWin Interaction**: 
    - The "Maximize on Monitor N" option launches `alacritty` with a special window class: `--class alacritty-monitor-N,Alacritty`.
    - Pre-installed KWin rules match this class and force the window to:
        - Screen N
        - Maximize Vertically & Horizontally
        - Remove Borders (optional, handled by KWin preferences mostly)

## Installation

1.  Run the install script:
    ```bash
    ./install.sh
    ```
    This will:
    - Update your `~/.config/kwinrulesrc` with the necessary rules.
    - Reload KWin.
    - Install a desktop entry `Alacritty Maximizer` to your applications menu.

## Requirements
- Linux with KDE Plasma (KWin)
- Python 3
- PyQt6 (`sudo pacman -S python-pyqt6` or `pip install PyQt6`)
- Alacritty

## Files
- `main.py`: The PyQt GUI launcher.
- `install_kwin_rules.py`: Script to inject KWin rules.
- `install.sh`: Master installation script.
