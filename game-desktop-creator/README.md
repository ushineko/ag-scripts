# Game Desktop Creator

**Version 1.1.0**

A PyQt6 GUI application that creates start menu launchers for your installed games on Linux. Supports **Steam** and **Heroic Games Launcher** (Epic Games Store, GOG).

## Table of Contents
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [How It Works](#how-it-works)
- [File Locations](#file-locations)
- [Uninstallation](#uninstallation)
- [Changelog](#changelog)

## Features

- Discovers installed games from multiple sources:
  - **Steam** - All library folders
  - **Epic Games** - Via Heroic Games Launcher
  - **GOG** - Via Heroic Games Launcher
- Creates `.desktop` launcher files with game icons
- Shows source tags ([Steam], [Epic], [GOG]) for each game
- Supports installing/removing launchers in bulk
- Shows which games already have launchers installed

## Requirements

- Python 3.x
- PyQt6
- Steam and/or Heroic Games Launcher installed with games

## Installation

```bash
cd game-desktop-creator
./install.sh
```

This installs the application to your start menu. You can then launch "Game Desktop Creator" from your applications menu.

## Usage

1. Launch the application from your start menu or run directly:
   ```bash
   python3 game_desktop_creator.py
   ```

2. The app will display all installed games from Steam and Heroic

3. Check the boxes next to games you want to add to your start menu

4. Click **Install Selected** to create desktop launchers

5. Click **Remove Selected** to remove launchers for checked games

6. Click **Refresh** to rescan for games

### Buttons

| Button | Action |
|--------|--------|
| Refresh | Rescan all sources for games |
| Install Selected | Create desktop files for checked games |
| Remove Selected | Remove desktop files for checked games |
| Select All | Check all games in the list |
| Select None | Uncheck all games in the list |

## How It Works

### Steam Games
- Reads `~/.steam/steam/steamapps/libraryfolders.vdf` to find all library paths
- Parses `appmanifest_*.acf` files in each library to get game info
- Launchers use `steam://rungameid/<appid>` URL

### Heroic Games (Epic/GOG)
- Reads `~/.config/heroic/legendaryConfig/legendary/installed.json` for Epic games
- Reads `~/.config/heroic/gogdlConfig/gog/installed.json` for GOG games
- Launchers use `heroic://launch/<runner>/<app_name>` URL

## File Locations

| File Type | Location |
|-----------|----------|
| Steam launchers | `~/.local/share/applications/steam-game-<appid>.desktop` |
| Epic launchers | `~/.local/share/applications/heroic-epic-<app_name>.desktop` |
| GOG launchers | `~/.local/share/applications/heroic-gog-<app_name>.desktop` |
| Game icons | `~/.local/share/icons/hicolor/256x256/apps/` |

## Uninstallation

```bash
./uninstall.sh
```

This removes the application from your start menu and optionally removes all game launchers created by the app.

## Changelog

### 1.1.0
- Added Heroic Games Launcher support (Epic Games, GOG)
- Renamed project from "Steam Desktop File Creator" to "Game Desktop Creator"
- Added source tags ([Steam], [Epic], [GOG]) to game list
- Status bar now shows game counts per source

### 1.0.0
- Initial release
- Steam library discovery and game scanning
- Desktop file creation with game icons
- Bulk install/remove support
