# Steam Desktop File Creator

**Version 1.0.0**

A PyQt6 GUI application that creates start menu launchers for your installed Steam games on Linux.

## Features

- Automatically discovers all Steam library folders
- Scans for installed games across multiple drives
- Creates `.desktop` launcher files with game icons
- Supports installing/removing launchers in bulk
- Shows which games already have launchers installed

## Requirements

- Python 3.x
- PyQt6
- Steam installed with at least one game

## Installation

```bash
cd steam-desktop-file-creator
./install.sh
```

This installs the application to your start menu. You can then launch "Steam Desktop Creator" from your applications menu.

## Usage

1. Launch the application from your start menu or run directly:
   ```bash
   python3 steam_desktop_creator.py
   ```

2. The app will display all installed Steam games

3. Check the boxes next to games you want to add to your start menu

4. Click **Install Selected** to create desktop launchers

5. Click **Remove Selected** to remove launchers for checked games

6. Click **Refresh** to rescan your Steam libraries

### Buttons

| Button | Action |
|--------|--------|
| Refresh | Rescan Steam libraries for games |
| Install Selected | Create desktop files for checked games |
| Remove Selected | Remove desktop files for checked games |
| Select All | Check all games in the list |
| Select None | Uncheck all games in the list |

## How It Works

- Reads `~/.steam/steam/steamapps/libraryfolders.vdf` to find all library paths
- Parses `appmanifest_*.acf` files in each library to get game info
- Creates `.desktop` files in `~/.local/share/applications/`
- Copies game icons from Steam's cache to `~/.local/share/icons/`
- Launchers use `steam://rungameid/<appid>` URL to start games

## File Locations

| File Type | Location |
|-----------|----------|
| Game launchers | `~/.local/share/applications/steam-game-<appid>.desktop` |
| Game icons | `~/.local/share/icons/hicolor/256x256/apps/steam-game-<appid>.png` |

## Uninstallation

```bash
./uninstall.sh
```

This removes the application from your start menu and optionally removes all game launchers created by the app.

## Changelog

### 1.0.0
- Initial release
- Steam library discovery and game scanning
- Desktop file creation with game icons
- Bulk install/remove support
