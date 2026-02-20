# DHCP Lease Monitor

Frameless PyQt6 desktop widget for monitoring `dnsmasq` DHCP leases in real time on Linux/KDE.

## Version

`1.1.1`

## Table of Contents
- [Features](#features)
- [Requirements](#requirements)
- [Usage](#usage)
- [Installation](#installation)
- [Configuration](#configuration)
- [Testing](#testing)

## Features

- Reads `dnsmasq` lease data from `/var/lib/misc/dnsmasq.leases` (or custom path)
- Realtime refresh via `inotify` plus 30s fallback timer
- Sorting model:
  - Static/fixed leases pinned to the top (special color)
  - Active leases sorted by most recent activity (expiry descending)
  - Expired leases shown dimmed at the bottom
- Device type inference from hostname + OUI vendor heuristics
- Reverse-DNS (`PTR`) lookup shown for each lease IP (with cache)
- Freedesktop themed icons per device type (`QIcon.fromTheme`)
- Click a lease row for detailed popup stats and live countdown
- Right-click menus:
  - Widget: opacity, font scale, refresh, quit
  - Lease row: copy IP/MAC
- Runtime serving-interface detection from system routing table
- Single-instance lock via `QLockFile`
- Structured rotating logs via `structlog`

## Requirements

- Python 3.10+
- `PyQt6`
- `structlog`
- `mac-vendor-lookup` (recommended for offline OUI names)
- `inotify_simple` (recommended for realtime updates)

Install with pip:

```bash
pip install PyQt6 structlog mac-vendor-lookup inotify-simple
```

## Usage

```bash
python3 dhcp-lease-monitor.py
```

Debug mode:

```bash
python3 dhcp-lease-monitor.py --debug
```

Override lease file path:

```bash
python3 dhcp-lease-monitor.py --lease-file /path/to/dnsmasq.leases
```

## Installation

```bash
chmod +x install.sh uninstall.sh
./install.sh
```

`install.sh` can place the desktop entry in autostart, applications menu, or both.  
On KDE Plasma it also installs the KWin always-on-top rule (`install_kwin_rule.py`).

## Configuration

Settings are stored at:

`~/.config/dhcp-lease-monitor.json`

Default values:

```json
{
  "opacity": 0.95,
  "font_scale": 1.0,
  "lease_file": "/var/lib/misc/dnsmasq.leases",
  "lease_duration_hours": 24,
  "show_expired": true
}
```

Logs are stored under:

`~/.local/state/dhcp-lease-monitor/`

- `dhcp_lease_monitor.log`
- `stderr.log`
- `crash.log`

## Testing

```bash
pytest -q tests/test_device_identifier.py tests/test_lease_reader.py
```
