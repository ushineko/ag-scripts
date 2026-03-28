# vscode-gather

Gathers all VS Code windows onto a single monitor and maximizes them. Uses KWin scripting via D-Bus — works on KDE Plasma 6 / Wayland.

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [How It Works](#how-it-works)
- [Uninstallation](#uninstallation)
- [Changelog](#changelog)

## Features

- Auto-detects the primary monitor via `kscreen-doctor`
- Moves all VS Code windows to the target monitor and maximizes them
- Configurable target output (`--output`) and window class (`--class`)
- Dry-run mode to inspect the generated KWin script
- Debug mode with KWin journal output

## Requirements

- KDE Plasma 6 (Wayland)
- `qdbus6` (from `qt6-tools`)
- `kscreen-doctor` (from `kscreen`)

## Installation

```bash
./install.sh
```

This symlinks `gather.sh` to `~/bin/vscode-gather`.

## Usage

```bash
# Gather all VS Code windows to the primary monitor
vscode-gather

# Target a specific output
vscode-gather --output DP-2

# Match a different window class (e.g. all Chromium windows)
vscode-gather --class chromium

# Show the generated KWin script without running it
vscode-gather --dry-run

# Debug mode (prints KWin journal output)
vscode-gather --debug
```

## How It Works

1. Detects the primary monitor by parsing `kscreen-doctor --outputs` (priority 1)
2. Generates a KWin JavaScript snippet that:
   - Finds the target output in `workspace.screens`
   - Iterates all windows matching the target `resourceClass`
   - Moves each window via `workspace.sendClientToScreen()`
   - Maximizes each window via `setMaximize(true, true)`
3. Loads the script into KWin via D-Bus (`org.kde.kwin.Scripting.loadScript`)
4. Runs and unloads the script, cleaning up the temporary file

## Uninstallation

```bash
./uninstall.sh
```

## Changelog

### v1.0

- Initial release
- Auto-detect primary monitor via kscreen-doctor
- Move + maximize all VS Code windows via KWin scripting D-Bus API
- Support for `--output`, `--class`, `--dry-run`, `--debug` flags
