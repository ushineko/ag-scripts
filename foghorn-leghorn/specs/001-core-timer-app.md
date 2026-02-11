# Spec 001: Core Timer Application

**Status: COMPLETE**

## Description

Foghorn Leghorn is an always-on-top countdown timer application for KDE Plasma / CachyOS. Users create named countdown timers that tick down in real time. When a timer expires, the app fires a system notification and plays an attention-grabbing sound (foghorn by default). The window stays on top of all other windows, fonts are large by default but adjustable, and the app minimizes to the system tray so timers keep running when the window is closed.

## Requirements

### Window & Display
- Always-on-top PyQt6 window (Qt.WindowType.WindowStaysOnTopHint)
- Large, readable countdown font (default ~48pt mono/digital style, minimum 16pt)
- Font size adjustable via slider or +/- controls in a settings area
- Compact layout: each timer is a single row showing name, remaining time, and action buttons
- Window remembers its position and size between sessions

### Timer Management
- Add new timers with a name and duration (hours, minutes, seconds)
- Edit existing timers (name, duration) in place
- Delete timers with confirmation
- Pause / resume individual timers
- Reset a timer to its original duration
- Drag-and-drop or up/down button reordering of timers
- Multiple timers can run simultaneously
- Timer state persists across application restarts (save to config)

### System Tray Integration
- Minimize to system tray on window close (do not quit)
- Tray icon with context menu: Show/Hide window, Quit
- Tray tooltip shows number of active timers
- Closing the window hides to tray; explicit "Quit" exits the app
- Timers continue ticking in the background when window is hidden

### Notifications & Sounds
- When a timer expires:
  - Fire a system notification via `notify-send` (or Qt notification) with the timer name
  - Play an alarm sound
- Default sound: foghorn (bundled .wav or .ogg file)
- Alternative bundled sounds: Wilhelm scream, air horn
- User can select a custom sound file per timer (or use global default)
- Sound volume follows system volume (no in-app volume control needed)
- Global setting to enable/disable sounds (notifications always fire)

### Configuration
- Config stored at `~/.config/foghorn-leghorn/config.json`
- Persisted settings: window geometry, font size, timer list (name, duration, order, sound choice), global sound on/off
- Timers with remaining time > 0 are saved so they survive restarts (save elapsed time)

### Platform
- Target: CachyOS / KDE Plasma 6
- Toolkit: PyQt6
- Audio playback: PyQt6 multimedia or `paplay` / `aplay` fallback
- System Python (`/usr/bin/python3`), no conda

## Acceptance Criteria

- [ ] Application launches as an always-on-top window with a timer list
- [ ] User can add a new timer with name and duration (h/m/s)
- [ ] User can edit a timer's name and duration
- [ ] User can delete a timer (with confirmation)
- [ ] User can pause, resume, and reset individual timers
- [ ] Multiple timers run simultaneously with independent countdowns
- [ ] Timer order can be rearranged (drag-and-drop or up/down buttons)
- [ ] Font size is large by default (~48pt) and adjustable
- [ ] Window minimizes to system tray on close; timers keep running
- [ ] Tray icon context menu offers Show, Hide, and Quit actions
- [ ] Expired timer fires a desktop notification with the timer name
- [ ] Expired timer plays the selected alarm sound
- [ ] Three bundled sounds available: foghorn (default), Wilhelm scream, air horn
- [ ] User can select a custom sound file for any timer
- [ ] Global sound mute toggle works
- [ ] Timer state (including remaining time for active timers) persists across restarts
- [ ] Window geometry and font size persist across restarts
- [ ] Config stored at `~/.config/foghorn-leghorn/config.json`
- [ ] Application runs on CachyOS / KDE Plasma 6 with system Python
- [ ] Tests exist and pass (`pytest`)
- [ ] `install.sh` creates desktop entry and symlink
- [ ] `uninstall.sh` removes all installed files
- [ ] README.md documents features, installation, usage, and configuration

## Architecture

### File Structure
```
foghorn-leghorn/
├── README.md
├── install.sh
├── uninstall.sh
├── foghorn_leghorn.py          # Main application (single file to start)
├── sounds/                     # Bundled alarm sounds
│   ├── foghorn.wav
│   ├── wilhelm_scream.wav
│   └── air_horn.wav
├── foghorn-leghorn.desktop     # Desktop entry
├── specs/
│   └── 001-core-timer-app.md
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   └── test_unit_foghorn_leghorn.py
└── validation-reports/
```

### Key Classes
- **ConfigManager** - Load/save JSON config, manage defaults
- **Timer (dataclass)** - name, duration_seconds, remaining_seconds, sound_path, is_running, is_paused
- **TimerEngine** - QObject with QTimer ticking at 1s intervals, manages all Timer instances, emits signals on tick/expire
- **TimerRowWidget** - Single timer row: label, countdown display, pause/resume/reset/delete buttons
- **TimerListWidget** - Scrollable list of TimerRowWidget items, supports reordering
- **AddTimerDialog** - Dialog for creating/editing a timer (name, h/m/s spinboxes, sound picker)
- **MainWindow** - Always-on-top QMainWindow with TimerListWidget, add button, font size control, settings
- **TrayManager** - QSystemTrayIcon with context menu, notification dispatch
- **SoundPlayer** - Plays alarm sounds via QMediaPlayer or subprocess fallback

### Sound Sources
- Bundled sounds will be sourced from freely licensed audio files
- For the spec: placeholder .wav files can be generated via `sox` or downloaded from freesound.org
- Final sounds to be confirmed during implementation

## Implementation Notes

- Use `QTimer` with 1-second interval for countdown ticks (sufficient precision for a reminder app)
- Save timer state on every tick is excessive; save on pause, add, delete, edit, and on app quit (via `closeEvent` and tray quit)
- For drag-and-drop reordering, `QListWidget` with `setDragDropMode` is the simplest approach
- Notifications: prefer `QSystemTrayIcon.showMessage()` for cross-platform Qt integration, with `notify-send` as fallback for richer KDE notifications
- Sound playback: try `QMediaPlayer` (PyQt6.QtMultimedia) first; fall back to `paplay` (PulseAudio/PipeWire) if multimedia module unavailable
- Always-on-top: `setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Window)`
