# vscode-gather

Gathers all VS Code windows onto a single monitor and maximizes them.

- **Linux**: KWin scripting via D-Bus (KDE Plasma 6 / Wayland)
- **macOS**: AppleScript via osascript (requires Accessibility access)

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [How It Works](#how-it-works)
- [macOS Notes](#macos-notes)
- [Uninstallation](#uninstallation)
- [Changelog](#changelog)

## Features

- Auto-detects the primary monitor
- Moves all VS Code windows to the target monitor and maximizes them
- Configurable target output (`--output`) and window class (`--class`)
- List available displays with `--list-outputs`
- Dry-run mode to inspect the generated script
- Debug mode with post-gather window state
- Cross-platform: Linux (KDE Plasma 6) and macOS

## Requirements

### Linux

- KDE Plasma 6 (Wayland)
- `qdbus6` (from `qt6-tools`)
- `kscreen-doctor` (from `kscreen`)

### macOS

- Accessibility access granted to the terminal app (System Settings → Privacy & Security → Accessibility)
- No additional dependencies (uses built-in `osascript` and `system_profiler`)

## Installation

```bash
./install.sh
```

- **Linux**: Symlinks to `~/bin/vscode-gather`
- **macOS**: Symlinks to `/usr/local/bin/vscode-gather`. The installer checks for Accessibility access and opens System Settings if needed.

## Usage

```bash
# Gather all VS Code windows to the primary monitor
vscode-gather

# List available displays
vscode-gather --list-outputs

# Target a specific output
vscode-gather --output DP-2          # Linux
vscode-gather --output "Built-in Retina Display"  # macOS

# Match a different window class/process (e.g. all Chromium windows)
vscode-gather --class chromium

# Show the generated script without running it
vscode-gather --dry-run

# Debug mode (prints window state after gathering)
vscode-gather --debug
```

## How It Works

### Linux (KDE Plasma 6)

1. Detects the primary monitor by parsing `kscreen-doctor --outputs` (priority 1)
2. Generates a KWin JavaScript snippet that iterates all windows matching the target `resourceClass`, moves each to the target output, and maximizes them
3. Loads and runs the script via D-Bus (`org.kde.kwin.Scripting`)

### macOS

1. Detects the primary display via `NSScreen.mainScreen` (JXA/osascript)
2. Gets the usable display bounds via `NSScreen.visibleFrame` (excludes menu bar and dock)
3. Generates an AppleScript that iterates all windows of the target process, sets their position and size to fill the display

## macOS Notes

- **Accessibility access is required.** Without it, the script exits with error -25211. Grant access in System Settings → Privacy & Security → Accessibility for your terminal app (Terminal.app, iTerm2, etc.).
- **"Maximize" means resize-to-fill**, not macOS fullscreen (green button). Windows are resized to fill the display bounds without entering a separate Space.
- **Display names** come from `NSScreen.localizedName` (e.g., "Built-in Retina Display", "DELL U2723QE"). Use `--list-outputs` to see available names.
- **`code` CLI on PATH**: VS Code must be on PATH. If not, run "Shell Command: Install 'code' command in PATH" from the VS Code command palette.

## Uninstallation

```bash
./uninstall.sh
```

## Changelog

### v2.0

- Add macOS support via AppleScript/JXA (NSScreen for display detection, System Events for window manipulation)
- Add `--list-outputs` flag to show available displays
- Cross-platform display detection (kscreen-doctor on Linux, NSScreen on macOS)
- Platform detection via `uname -s`
- Install/uninstall scripts handle both Linux and macOS

### v1.0

- Initial release
- Auto-detect primary monitor via kscreen-doctor
- Move + maximize all VS Code windows via KWin scripting D-Bus API
- Support for `--output`, `--class`, `--dry-run`, `--debug` flags
