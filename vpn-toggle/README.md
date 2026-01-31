# VPN Toggle Script

A GUI-friendly Bash script to manage NetworkManager VPN connections. Designed for binding to a keyboard shortcut.

## Table of Contents
- [Features](#features)
- [Usage](#usage)
- [Integration](#integration)
- [Changelog](#changelog)

## Features
- **Smart Detection**: Fuzzy-matches connection names (e.g., "vegas" matches "us_las_vegas...").
- **GUI Menu**: Pops up a dialog (using `kdialog` or `zenity`) to:
    - **Enable**: Connect if disconnected.
    - **Disable**: Disconnect if connected.
    - **Bounce**: Restart the connection (useful for stuck routes).
    - **Config**: Open system network settings.
- **Visual Feedback**: Sends desktop notifications on status changes.

## Usage
### Basic
Run with default connection (searches for "us_las_vegas"):
```bash
./toggle_vpn.sh
```

### Specific Connection
Pass a partial name string to control a specific VPN:
```bash
./toggle_vpn.sh "office"
```

## Integration
Bind this script to a global hotkey (e.g., Meta+V) in your desktop environment (KDE/GNOME) for quick access.

## Changelog

### v1.0.0
- Initial release
- Fuzzy connection name matching
- GUI menu via kdialog/zenity
- Enable/Disable/Bounce/Config actions
- Desktop notifications
