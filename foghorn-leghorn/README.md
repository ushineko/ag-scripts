# Foghorn Leghorn

An always-on-top countdown timer for KDE Plasma with system tray integration and attention-grabbing alarm sounds.

## Table of Contents

- [Features](#features)
- [Screenshots](#screenshots)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Sounds](#sounds)
- [Changelog](#changelog)

## Features

- **Always-on-Top Window**: Timer display stays visible above other windows
- **Large Countdown Font**: Default 48pt monospace, adjustable from 16pt to 72pt
- **Multiple Simultaneous Timers**: Run any number of independent countdowns
- **Timer Controls**: Start, pause, resume, reset, edit, and delete individual timers
- **Reorderable Timer List**: Move timers up and down to organize by priority
- **System Tray Integration**: Minimizes to tray on close; timers keep running in the background
- **Desktop Notifications**: Fires system notifications via both Qt and `notify-send` when timers expire
- **Alarm Sounds**: Three bundled sounds (foghorn, Wilhelm scream, air horn) plus custom sound file support
- **Global Sound Mute**: Toggle all alarm sounds on/off
- **Persistent State**: Window position, font size, timer list, and remaining time survive restarts
- **Per-Timer Sound Selection**: Each timer can use a different alarm sound

## Screenshots

*Coming soon*

## Installation

### Requirements

- Python 3.12+
- PyQt6
- KDE Plasma 6 (CachyOS or similar)

### Install

```bash
./install.sh
```

This creates a symlink in `~/.local/bin/` and a desktop entry in `~/.local/share/applications/`.

### Uninstall

```bash
./uninstall.sh
```

## Usage

Launch from the application menu or command line:

```bash
foghorn-leghorn
```

### Adding a Timer

1. Click **+ Add Timer**
2. Enter a name and set the duration (hours, minutes, seconds)
3. Select an alarm sound (Foghorn, Wilhelm Scream, Air Horn, or Custom)
4. Click **OK** - the timer starts immediately

### Timer Controls

| Button | Action |
|--------|--------|
| **Start/Pause/Resume** | Toggle timer running state |
| **Reset** | Reset countdown to original duration |
| **Edit** | Change name, duration, or sound |
| **Del** | Delete the timer (with confirmation) |
| **▲ / ▼** | Reorder timers in the list |

### System Tray

- Closing the window hides it to the tray - timers continue running
- Left-click the tray icon to show/hide the window
- Right-click for context menu: Show, Hide, Quit
- The tooltip shows the number of active timers

### Font Size

Use the **Font** slider in the top bar to adjust the countdown display size (16-72pt).

### Sound Mute

Uncheck the **Sound** checkbox to mute alarm sounds. Desktop notifications still fire.

## Configuration

Settings are stored at:

```
~/.config/foghorn-leghorn/config.json
```

Persisted data includes:
- Window position and size
- Font size
- Sound enabled/disabled
- Full timer list with remaining times

## Sounds

### Bundled Sounds

| Sound | Description |
|-------|-------------|
| **Foghorn** | Low-frequency horn blast (default) |
| **Wilhelm Scream** | Descending frequency sweep |
| **Air Horn** | Dual-tone air horn blast |

### Custom Sounds

Select "Custom..." in the sound picker when adding/editing a timer, then browse for a `.wav`, `.ogg`, `.mp3`, or `.flac` file.

## Changelog

### v1.0.0
- Initial release
- Always-on-top countdown timer window
- Multiple simultaneous timers with independent controls
- System tray integration with background timer operation
- Desktop notifications on timer expiry
- Three bundled alarm sounds: foghorn, Wilhelm scream, air horn
- Custom sound file support per timer
- Font size adjustment (16-72pt)
- Timer reordering via up/down buttons
- Persistent state across restarts
