# WhoaPipe

GUI launcher manager for [waypipe](https://gitlab.freedesktop.org/mstoeckl/waypipe) SSH remote Wayland applications.

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Changelog](#changelog)

## Features

- **Profile management** — Define per-app launcher profiles (host, command, waypipe flags) with auto-save/load
- **Remote app browser** — Discover installed applications on remote hosts via `.desktop` file parsing, displayed in a searchable icon grid
- **Remote icon caching** — Fetches application icons from remote hosts and caches them locally
- **SSH connectivity testing** — Test individual or all host connections before launching
- **Waypipe flag UI** — Checkboxes and dropdowns for `--no-gpu`, `--compress`, `--video`, `--debug`, `--oneshot`, `--xwls`, and extra flags
- **Failure detection** — Detects rapid exits and error output with diagnostic hints (GPU/DMABUF, Electron/X11, command not found, etc.)
- **Run in terminal** — Wraps TUI/CLI apps in `foot -e` for forwarding via waypipe
- **Force dark theme** — Sets GTK/libadwaita/Qt dark mode environment variables on the remote app
- **Real-time log capture** — Timestamped waypipe output in a log panel
- **Default host** — Remembers the last-used host for new profiles
- **Desktop integration** — `.desktop` file for application menu launchers

## Requirements

- Python 3.10+
- PyQt6
- waypipe (local and remote)
- SSH key-based authentication to remote hosts
- foot terminal (for "Run in terminal" feature)

## Installation

```bash
./install.sh
```

This copies the `.desktop` file to `~/.local/share/applications/` and updates the desktop database.

To uninstall:

```bash
./uninstall.sh
```

## Usage

Launch from the application menu or directly:

```bash
python3 whoapipe.py
```

1. **Add a profile** — Click "Add", enter host and command (or click "Browse..." to discover remote apps)
2. **Configure flags** — Set waypipe options, enable dark theme or terminal mode as needed
3. **Launch** — Double-click an entry or select it and click "Launch"
4. **Monitor** — Check the log panel for waypipe output and diagnostics

## Changelog

### v1.0 — Initial Release

- Profile management with auto-save/load and JSON config migration
- Remote `.desktop` file browser with searchable icon grid
- Remote icon caching via SSH + base64
- SSH connectivity testing (single and batch)
- Waypipe flag checkboxes (`--no-gpu`, `--compress`, `--video`, `--debug`, `--oneshot`, `--xwls`)
- Real-time log capture with timestamps
- Failure detection with diagnostic hints
- Run-in-terminal support (`foot -e` wrapper)
- Force dark theme (GTK/libadwaita/Qt via xdgdesktopportal)
- Default host setting
- Desktop launcher with install/uninstall scripts
- Help & About dialog
