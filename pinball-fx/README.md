# Pinball FX Window Fixer

A utility to force Pinball FX to run on your portrait monitor.

Since launching the game via a custom script proved unstable, this tool is designed to be run **manually after you launch the game** via Heroic/Steam.

## Features
- Detects your portrait monitor automatically.
- Forces the running "Pinball FX" window to that monitor and fullscreen mode.
- Persistent fix (writes to KWin rules).

## Installation

```bash
./install.sh
```

## Usage
1.  Launch **Pinball FX** normally (e.g., from Heroic Launcher).
2.  Wait for the game window to appear.
3.  Run **"Fix Pinball Window"** from your application menu (or search for it).
    - You can also bind this to a hotkey using KDE's "Edit Application..." -> "Keyboard Shortcuts".

## Uninstallation

```bash
./uninstall.sh
```
