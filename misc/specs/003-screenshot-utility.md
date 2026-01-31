# Spec 003: Screenshot Utility

**Status: COMPLETE**

## Description
A reusable utility script for capturing screenshots of applications for README documentation. Uses kdotool for window management and spectacle for screenshots on KDE.

## Requirements
- Accept application name/class and output path as arguments
- Check if application is running
- If not running, optionally launch it
- Bring window to front and ensure visible
- Wait for window to settle
- Capture screenshot of just that window
- Save to specified output path

## Acceptance Criteria
- [x] Script accepts app identifier and output path
- [x] Finds running window by class name or title
- [x] Brings window to front using kdotool
- [x] Captures window screenshot with spectacle
- [x] Supports optional launch command if app not running
- [x] Provides clear error messages
- [x] Works on KDE Wayland

## Usage Example
```bash
# Screenshot a running app
./capture_window_screenshot.sh "peripheral-battery-monitor" assets/screenshot.png

# Launch if not running, then screenshot
./capture_window_screenshot.sh "peripheral-battery-monitor" assets/screenshot.png --launch "python3 peripheral-battery.py"
```

## Implementation Notes
Uses kdotool for window manipulation (KDE-native, Wayland-compatible) and spectacle for screenshots.
