# display-mirror-toggle

Toggle a KDE Plasma 6 / Wayland display mirror relationship between two outputs on or off, disabling/enabling the source output in the same atomic kscreen-doctor call.

**Version:** 1.0.0

## Table of Contents

- [Overview](#overview)
- [Problem](#problem)
- [Installation](#installation)
- [Usage](#usage)
- [Options](#options)
- [Examples](#examples)
- [Use Case: OLED Pixel-Clean Workaround](#use-case-oled-pixel-clean-workaround)
- [Uninstallation](#uninstallation)
- [Changelog](#changelog)

## Overview

This is a thin wrapper around `kscreen-doctor` that handles the two gotchas that bit during manual debugging:

- The setter verb is `mirror`, not `replicate` or `replication`, despite `kscreen-doctor -o` displaying the field as "replication source".
- Disabling the source while the replica still points at it fails with a `Position of enabled output ... is negative` error because KDE recomputes the replica's geometry from the now-disabled source. The script always pairs the verbs in one atomic call so KDE validates the final state.

The script also auto-detects current state, so the default (no-arg) invocation is a clean toggle suitable for binding to a hotkey.

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

Creates a symlink at `~/bin/display-mirror-toggle`.

## Usage

```bash
display-mirror-toggle [OPTIONS]
```

With no mode flag, toggles between mirror-active and mirror-off states.

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

**Bind to a KDE custom shortcut:** add `~/bin/display-mirror-toggle` as a custom shortcut command in System Settings → Shortcuts → Custom Shortcuts.

## Use Case: OLED Pixel-Clean Workaround

The default source/replica match the FUERAN HDMI dummy plug + Philips 42M2N8900 OLED setup documented in `~/git/sysadmin/docs/sunshine-moonlight-setup.md`. With the mirror active, the OLED can pixel-clean (full power-off) without dropping the captured framebuffer Sunshine/Moonlight is streaming, because the dummy stays connected.

When the mirror isn't needed (sitting at the desk, no remote streaming planned), this utility provides a quick way to turn it off — and a quick way to turn it back on when needed again.

## Uninstallation

```bash
./uninstall.sh
```

## Changelog

### v1.0.0
- Initial release
- Toggle, `--enable`, `--disable`, `--status` modes
- Configurable source/replica via `--source` / `--replica`
- Atomic `kscreen-doctor` invocation (avoids replica-geometry error on disable)
- ANSI-stripping parser for `kscreen-doctor -o` state detection
- Idempotent: re-running in the current state is a no-op with informational output
