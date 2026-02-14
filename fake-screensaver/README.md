# Fake Screensaver

A simple "poor man's screensaver" that displays a black fullscreen window. Unlike a real screensaver or the HTML version, this PyQt application **keeps the mouse cursor visible**, which is useful for certain remote desktop or VM scenarios where you want to hide the content but keep mouse interaction visible or active.

## Table of Contents
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Global Hotkey (KDE Plasma)](#global-hotkey-kde-plasma)
- [Changelog](#changelog)

## Features
- **Black Fullscreen**: Covers the entire monitor with black.
- **Visible Cursor**: Does not hide the mouse pointer.
- **Easy Exit**: Press `Esc` to close.
- **Easter Egg**: Press `B` to toggle the "Blue Screen of Delight" (a parody BSOD).

## Requirements
- Python 3
- PyQt6

```bash
pip install PyQt6
```

## Installation

```bash
./install.sh
```

This installs a desktop entry so "Fake Screensaver" appears in your applications menu.

Or run directly without installing:
```bash
./fake_screensaver.py
```

## Global Hotkey (KDE Plasma)

To activate, you can bind this script to a global hotkey (e.g., `Meta+L` or `Meta+S`).

1.  Open **System Settings** -> **Shortcuts** -> **Custom Shortcuts**.
2.  Click **Add New** -> **Global Shortcut** -> **Command/URL**.
3.  Name it (e.g., "Fake Screensaver").
4.  In the **Trigger** tab, set your desired shortcut key.
5.  In the **Action** tab, enter the full path to the script in the **Command/URL** field:
    ```bash
    /home/nverenin/git/ag-scripts/fake-screensaver/fake_screensaver.py
    ```
    If it opens on the wrong screen, or you want to blank specific screens, you can use `--screen`:
    ```bash
    # Blank specific screens (e.g. index 0 and 2)
    /home/nverenin/git/ag-scripts/fake-screensaver/fake_screensaver.py --screen 0 2
    
    # Blank ALL screens (default if no argument provided)
    /home/nverenin/git/ag-scripts/fake-screensaver/fake_screensaver.py
    ```
    *(Run `./fake_screensaver.py` in a terminal to see available screen indices).*

## Changelog

### v1.2.0
- Added "Blue Screen of Delight" easter egg (press `B` to toggle)

### v1.1.1
- Added install.sh script

### v1.1.0
- Added multi-screen support via `--screen` flag
- Can now blank specific screens or all screens

### v1.0.0
- Initial release
- Black fullscreen window with visible cursor
- Desktop entry for application launcher
