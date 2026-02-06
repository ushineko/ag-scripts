# Spec 001: Bluetooth Reset Script

## Overview

A utility script to reset the Linux Bluetooth stack when it becomes unresponsive. BlueZ (the Linux Bluetooth daemon) can get stuck in a "busy" state after extended uptime, especially when devices like AirPods connect/disconnect frequently, causing HFP profile teardown errors.

## Problem Statement

- BlueZ daemon can become unresponsive while still appearing "active"
- Bluetooth scanning stops finding new devices
- Common with AirPods and Apple devices that don't cleanly disconnect
- Manual fix: `sudo systemctl restart bluetooth`

## Requirements

### Functional Requirements

- [x] Restart the bluetooth systemd service
- [x] Show bluetooth service status before and after restart
- [x] Support `--hard` flag for aggressive reset (rfkill toggle + service restart)
- [x] Support `--status` flag to show current state without restarting
- [x] Support `--check` flag to detect if bluetooth appears stuck (scan test)
- [x] Display connected devices before restart (warning about disconnection)
- [x] Exit with appropriate codes (0=success, 1=error, 2=bluetooth not available)

### Non-Functional Requirements

- [x] Script must work on systemd-based Linux distributions
- [x] Requires sudo/root for service restart
- [x] Should complete within 10 seconds for normal reset
- [x] Provide clear, concise output

## Acceptance Criteria

- [x] Running `bluetooth-reset` restarts the bluetooth service
- [x] Running `bluetooth-reset --status` shows service state and connected devices
- [x] Running `bluetooth-reset --hard` does rfkill toggle before service restart
- [x] Running `bluetooth-reset --check` attempts a scan and reports if stuck
- [x] Script warns user about connected devices before restarting
- [x] Script verifies bluetooth is available before attempting reset
- [x] Help text (`-h`/`--help`) documents all options
- [x] Works on Arch/CachyOS (systemd + bluez)

## Technical Design

### Language
Bash script (simple, no dependencies beyond systemd and bluez tools)

### Commands Used
- `systemctl restart bluetooth` - restart service
- `systemctl status bluetooth` - check status
- `bluetoothctl devices` - list known devices
- `bluetoothctl info <device>` - check if connected
- `rfkill block/unblock bluetooth` - hard toggle adapter
- `timeout` - prevent hangs during scan test

### Output Format
```
Bluetooth Reset Utility

Current Status:
  Service: active (running)
  Connected: Papa's AirPods Pro, Keychron K4 HE

WARNING: 2 device(s) will be disconnected.

Restarting bluetooth service...
Done.

New Status:
  Service: active (running)
  Connected: (none)
```

## File Structure

```
bluetooth-reset/
├── README.md
├── bluetooth-reset.sh
├── install.sh
├── uninstall.sh
├── specs/
│   └── 001-bluetooth-reset-script.md
└── tests/
    └── test_bluetooth_reset.sh
```

## Test Plan

- [x] Test `--help` outputs usage information
- [x] Test `--status` shows current state
- [x] Test exit code 2 when bluetooth service not found
- [x] Test warning message when devices connected
- [x] Test `--hard` calls rfkill commands

## Status

**Status: COMPLETE**

---

## Notes

Based on real troubleshooting session where BlueZ got stuck after 2+ days uptime with AirPods connect/disconnect cycles causing HFP profile errors.
