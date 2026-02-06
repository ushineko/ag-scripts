# bluetooth-reset

Reset the Linux Bluetooth stack when it becomes unresponsive.

**Version:** 1.0.0

## Table of Contents

- [Overview](#overview)
- [Problem](#problem)
- [Installation](#installation)
- [Usage](#usage)
- [Options](#options)
- [Examples](#examples)
- [Uninstallation](#uninstallation)
- [Changelog](#changelog)

## Overview

BlueZ (the Linux Bluetooth daemon) can get stuck in a "busy" state after extended uptime, especially when devices like AirPods connect/disconnect frequently. When this happens, Bluetooth scanning stops finding new devices even though the service appears active.

This utility provides a quick way to reset the Bluetooth stack and restore functionality.

## Problem

Symptoms of a stuck Bluetooth stack:
- `bluetoothctl scan on` finds no devices
- New devices won't pair
- Service shows as "active" but is unresponsive
- Logs show `Failed to set mode: Busy (0x0a)`

Common causes:
- Extended uptime (days without restart)
- Apple devices (AirPods) with unclean HFP profile disconnects
- Bluetooth device switching between multiple hosts

## Installation

```bash
./install.sh
```

This creates a symlink in `~/bin/bluetooth-reset`.

## Usage

```bash
bluetooth-reset [OPTIONS]
```

## Options

| Option | Description |
|--------|-------------|
| `-h, --help` | Show help message |
| `-v, --version` | Show version |
| `-s, --status` | Show current bluetooth status (no restart) |
| `-c, --check` | Check if bluetooth appears stuck (scan test) |
| `-H, --hard` | Hard reset: rfkill toggle + service restart |
| `-y, --yes` | Skip confirmation prompt |
| `-q, --quiet` | Minimal output |

## Examples

**Show current status:**
```bash
bluetooth-reset --status
```

**Check if Bluetooth is stuck:**
```bash
bluetooth-reset --check
```

**Normal restart (will prompt if devices connected):**
```bash
bluetooth-reset
```

**Hard reset (more aggressive, for stubborn issues):**
```bash
bluetooth-reset --hard
```

**Restart without confirmation:**
```bash
bluetooth-reset --yes
```

## Uninstallation

```bash
./uninstall.sh
```

## Changelog

### v1.0.0
- Initial release
- Basic restart functionality
- Status display
- Hard reset mode with rfkill
- Scan check to detect stuck state
- Connected device warnings
