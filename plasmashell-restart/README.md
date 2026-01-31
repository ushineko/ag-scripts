# Plasmashell Restart

**Version 1.1.0**

A script to restart or refresh the KDE Plasma shell without logging out. Useful when desktop widgets, panels, or the taskbar get stuck or stop responding.

## Table of Contents
- [Usage](#usage)
- [What it does](#what-it-does)
- [Requirements](#requirements)
- [Changelog](#changelog)

## Usage

```bash
# Full restart (default) - restarts plasmashell via systemd
./restart.sh

# Light refresh - refreshes shell via D-Bus without process restart
./restart.sh --refresh
```

### Options

| Option | Description |
| :----- | :---------- |
| `-r`, `--refresh` | Light refresh via D-Bus (no process restart) |
| `-f`, `--full` | Full restart via systemd (default) |
| `-h`, `--help` | Show help message |
| `-v`, `--version` | Show version |

## What it does

### Full Restart (default)
1. Uses `systemctl --user restart plasma-plasmashell.service` for proper D-Bus registration
2. Falls back to legacy `kquitapp6`/`kquitapp5` + `kstart` if systemd service is unavailable
3. Verifies the service started successfully

### Light Refresh
1. Sends a D-Bus message to refresh the shell in-place
2. No process restart required - faster for minor visual glitches

## Requirements

- KDE Plasma 6
- systemd (recommended) or `kstart` (fallback)

*Note: Contains fallback code for older setups, but only Plasma 6 is tested.*

## Changelog

### v1.1.0
- Added light refresh mode via D-Bus (`--refresh` flag)
- Added systemd-first restart approach
- Added version flag

### v1.0.0
- Initial release
- Basic plasmashell restart via kquitapp/kstart
