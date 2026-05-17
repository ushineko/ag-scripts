# display-mirror-toggle

Toggle a KDE Plasma 6 / Wayland display mirror relationship between two outputs on or off, disabling/enabling the source output in the same atomic kscreen-doctor call. Ships with a CLI for hotkey binding and a system-tray app for visual state + configuration.

**Version:** 1.1.0

## Table of Contents

- [Overview](#overview)
- [Problem](#problem)
- [Installation](#installation)
- [Usage](#usage)
  - [CLI](#cli)
  - [Tray application](#tray-application)
- [Options](#options)
- [Examples](#examples)
- [Use Case: OLED Pixel-Clean Workaround](#use-case-oled-pixel-clean-workaround)
- [Uninstallation](#uninstallation)
- [Changelog](#changelog)

## Overview

The CLI is a thin wrapper around `kscreen-doctor` that handles the two gotchas that bit during manual debugging:

- The setter verb is `mirror`, not `replicate` or `replication`, despite `kscreen-doctor -o` displaying the field as "replication source".
- Disabling the source while the replica still points at it fails with a `Position of enabled output ... is negative` error because KDE recomputes the replica's geometry from the now-disabled source. The script always pairs the verbs in one atomic call so KDE validates the final state.

The CLI auto-detects current state, so the default (no-arg) invocation is a clean toggle suitable for binding to a hotkey.

The tray app (added in v1.1) is a PyQt6 system-tray frontend that shells out to the CLI. It shows the live mirror state, exposes Toggle / Enable / Disable / Settings from the context menu, and registers a global hotkey via KDE's KGlobalAccel D-Bus interface (same approach as [vscode-launcher](../vscode-launcher/)).

## Problem

Direct `kscreen-doctor` usage:

```bash
# Wrong (KDE renders the field as "replication source" but the verb isn't 'replicate'):
kscreen-doctor output.DP-3.replicate.none output.HDMI-A-1.disable
#   Unable to parse arguments: output.DP-3.replicate.none

# Wrong (omitting the mirror clear leaves a dangling replica):
kscreen-doctor output.HDMI-A-1.disable
#   applying config failed! Position of enabled output DP-3 is negative (-2560, 0)

# Right (atomic, both verbs in one call):
kscreen-doctor output.DP-3.mirror.none output.HDMI-A-1.disable
```

Easy to get wrong twice in a row. This utility encapsulates the working command pair and adds the inverse for re-enable.

## Installation

```bash
./install.sh
```

Installs:

- `~/bin/display-mirror-toggle` — CLI symlink
- `~/.local/bin/display-mirror-tray` — tray launcher symlink
- `~/.local/share/applications/display-mirror-toggle.desktop` — application menu entry
- `~/.config/autostart/display-mirror-toggle.desktop` — autostart entry (tray launches at login)

The tray app needs PyQt6:

```bash
sudo pacman -S python-pyqt6   # Arch / CachyOS
```

## Usage

### CLI

```bash
display-mirror-toggle [OPTIONS]
```

With no mode flag, toggles between mirror-active and mirror-off states. Suitable for binding to a hotkey.

### Tray application

```bash
display-mirror-tray
```

The tray icon reflects mirror state (themed icons fall back to generic display icons if the symbolic ones aren't in your theme). Left-click toggles the mirror; right-click opens the context menu:

| Item | Action |
|------|--------|
| `Mirror: ON/OFF (...)` | Read-only status label |
| `Toggle now` | Same as CLI default (toggle) |
| `Enable mirror` | Same as CLI `--enable`. Disabled when already active. |
| `Disable mirror` | Same as CLI `--disable`. Disabled when already inactive. |
| `Settings…` | Edit source / replica connectors and the global hotkey |
| `About` | Version and current configuration |
| `Quit` | Exit the tray for this session (relaunch via the app menu or autostart at next login) |

The Settings dialog accepts any Qt key sequence (e.g. `Meta+Alt+M`, `Ctrl+Shift+F12`). Clearing the field removes the binding. Hotkey changes apply live whenever KDE's KGlobalAccel D-Bus service is reachable; otherwise they are saved and applied on next launch.

Config is persisted to `~/.config/display-mirror-toggle/config.json`:

```json
{
  "version": "1.1.0",
  "source": "HDMI-A-1",
  "replica": "DP-3",
  "global_hotkey": "Meta+Alt+M",
  "poll_interval_seconds": 5
}
```

The tray polls the engine every `poll_interval_seconds` to keep the icon and tooltip in sync if state changes from outside (e.g. another tool runs `kscreen-doctor`).

Only one tray instance runs at a time — re-running `display-mirror-tray` while one is already active shows a notification balloon instead of starting a duplicate.

## Options

| Option | Description |
|--------|-------------|
| `-h, --help` | Show help |
| `-v, --version` | Show version |
| `-s, --source CONNECTOR` | Source output (default: `HDMI-A-1`) |
| `-r, --replica CONNECTOR` | Replica output that mirrors the source (default: `DP-3`) |
| `--status` | Show current state, do not change anything |
| `--enable` | Force enable: source enabled + replica mirrors source |
| `--disable` | Force disable: clear mirror + disable source |
| `-q, --quiet` | Minimal output |

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Runtime error (kscreen-doctor failed, invalid args) |
| 2 | Dependency missing (kscreen-doctor not on PATH) |

## Examples

**Toggle the default mirror (HDMI-A-1 source, DP-3 replica):**

```bash
display-mirror-toggle
```

**Show current state without changing it:**

```bash
display-mirror-toggle --status
```

**Force the mirror off:**

```bash
display-mirror-toggle --disable
```

**Force the mirror on:**

```bash
display-mirror-toggle --enable
```

**Use a different source/replica pair:**

```bash
display-mirror-toggle --source HDMI-A-2 --replica DP-1
```

**Bind via the tray:** open the tray context menu → `Settings…` → record a key sequence. The binding is registered with KGlobalAccel and applies immediately.

**Bind manually (CLI only, no tray):** add `~/bin/display-mirror-toggle` as a custom shortcut command in System Settings → Shortcuts → Custom Shortcuts.

## Use Case: OLED Pixel-Clean Workaround

The default source/replica match the FUERAN HDMI dummy plug + Philips 42M2N8900 OLED setup documented in `~/git/sysadmin/docs/sunshine-moonlight-setup.md`. With the mirror active, the OLED can pixel-clean (full power-off) without dropping the captured framebuffer Sunshine/Moonlight is streaming, because the dummy stays connected.

When the mirror isn't needed (sitting at the desk, no remote streaming planned), this utility provides a quick way to turn it off — and a quick way to turn it back on when needed again.

## Uninstallation

```bash
./uninstall.sh
```

Removes both binaries' symlinks, the application/autostart `.desktop` entries, and stops any running tray instance. Pass `--purge-config` to also remove `~/.config/display-mirror-toggle/`.

## Changelog

### v1.1.0
- Add `display-mirror-tray` system-tray frontend (PyQt6)
- Tray icon reflects live mirror state; left-click toggles
- Settings dialog for source/replica connectors and global hotkey
- Global hotkey registered via KGlobalAccel D-Bus (KDE Plasma 6)
- Persistent JSON config at `~/.config/display-mirror-toggle/config.json`
- Single-instance guard via QLocalSocket
- Installer adds applications menu entry and autostart
- Uninstaller cleans tray artifacts and optionally purges config

### v1.0.0
- Initial release
- Toggle, `--enable`, `--disable`, `--status` modes
- Configurable source/replica via `--source` / `--replica`
- Atomic `kscreen-doctor` invocation (avoids replica-geometry error on disable)
- ANSI-stripping parser for `kscreen-doctor -o` state detection
- Idempotent: re-running in the current state is a no-op with informational output
