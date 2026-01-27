# Pinball FX Window Fixer

A utility to force Pinball FX to run on your portrait monitor.

Since launching the game via a custom script proved unstable, this tool is designed to be run **manually after you launch the game** via Heroic/Steam.

## Features
- Interactive menu to select the target monitor (Portrait or Landscape).
- Forces the "Pinball FX" window to the selected monitor and handles resizing.
- Uses "Force" KWin rules to ensure the window moves even if already open.
- Persistent fix (updates KWin rules).

## Installation

```bash
./install.sh
```

## Usage
1.  Launch **Pinball FX** normally.
2.  Run **"Fix Pinball Window"** from your application menu.
3.  Select the desired monitor from the menu that appears.
    -   You can switch between monitors at any time by running the tool again.
    -   Select "Disable/Uninstall Rule" to revert to default behavior.

### CLI Usage
You can also run the script from the terminal with arguments:
```bash
./configure_kwin.py --screen 0   # Target Screen 0
./configure_kwin.py --uninstall  # Remove rules
```

## Uninstallation

```bash
./uninstall.sh
```
