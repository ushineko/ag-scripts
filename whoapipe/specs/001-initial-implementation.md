# Spec 001: Initial Implementation

**Status: PENDING**

## Description

WhoaPipe is a PyQt6 GUI application that manages waypipe SSH connections for launching remote Wayland applications on the local desktop. It provides a persistent launcher interface where users can define per-app profiles (host + command), verify SSH connectivity, and launch remote apps with a double-click. All waypipe output (stdout/stderr) is captured and displayed in the UI for troubleshooting.

## Background

Waypipe forwards individual Wayland application windows over SSH. Usage pattern:
```
waypipe ssh <host> <command>
```

Key behaviors from testing:
- `--no-gpu` is required for GPU-accelerated apps (mpv, browsers with WebGL) to prevent dmabuf/Vulkan init crashes on the server side
- `--compress zstd` reduces bandwidth for video-heavy apps
- Apps appear as native local windows

## Requirements

### Core UI
- PyQt6 application with a main window containing a list/table of launcher entries
- Each launcher entry has: **Name** (display label), **Host** (SSH hostname/alias), **Command** (the remote application command), **Waypipe flags** (optional, e.g. `--no-gpu --compress zstd`)
- Double-click or select+launch button starts the remote app via waypipe
- Add, edit, and remove launcher entries via toolbar buttons or context menu
- System tray icon with show/hide toggle (optional, stretch goal)

### Profile Persistence
- Profiles auto-save on every change (add/edit/remove) to a JSON config file
- Config location: `~/.config/whoapipe/profiles.json`
- Profiles auto-load on application startup
- No manual save/load needed

### SSH Connectivity Check
- Before launching, verify SSH connectivity to the target host (non-interactive check, e.g. `ssh -o BatchMode=yes -o ConnectTimeout=5 <host> true`)
- Show clear pass/fail indicator per host in the UI
- Manual "Test Connection" button per entry or for all entries
- If connectivity fails at launch time, show error dialog instead of silently failing

### Waypipe Process Management
- Launch waypipe as a subprocess: `waypipe [flags] ssh <host> <command>`
- Track running processes per launcher entry (show running/stopped status)
- Allow launching multiple instances of the same entry
- Capture stdout and stderr from waypipe in real-time
- "Stop" button to terminate a running waypipe process

### Log/Debug Output Panel
- Collapsible or tabbed log panel at the bottom of the window
- Shows real-time waypipe stdout/stderr output per launched process
- Clear log button
- Timestamps on log lines
- Scrolls to latest output automatically

### Error Handling
- If `waypipe` binary is not found on the local system, show a clear error on startup
- If remote command fails, capture and display the error output
- Non-blocking — a failed launch should not freeze the UI

## Acceptance Criteria

- [ ] Application launches with a PyQt6 window showing a launcher list
- [ ] User can add a new launcher entry (name, host, command, waypipe flags)
- [ ] User can edit an existing launcher entry
- [ ] User can remove a launcher entry
- [ ] Profiles auto-save to `~/.config/whoapipe/profiles.json` on every change
- [ ] Profiles auto-load on startup
- [ ] SSH connectivity check runs before launch and shows pass/fail
- [ ] "Test Connection" button works for individual entries
- [ ] Double-click on an entry launches `waypipe [flags] ssh <host> <command>`
- [ ] Running/stopped status is visible per entry
- [ ] Waypipe stdout/stderr is captured and displayed in a log panel with timestamps
- [ ] "Stop" button terminates a running waypipe process
- [ ] Error shown if `waypipe` binary is not installed
- [ ] UI remains responsive during long-running processes (no blocking)
- [ ] Tests exist for profile save/load logic and SSH check logic
- [ ] Works on KDE Plasma Wayland (primary target environment)

## Technical Notes

- Use system Python (`/usr/bin/python3`) with PyQt6
- Use `QProcess` for subprocess management (integrates with Qt event loop, avoids threading for I/O)
- Config directory: `~/.config/whoapipe/`
- Single-instance enforcement not required for v1 (can add later)
- No KWin rules needed — waypipe-forwarded windows are managed by the compositor naturally

## Out of Scope (v1)

- Automatic SSH key setup or password management
- Port forwarding or tunnel management
- Remote file browsing
- Audio forwarding (waypipe handles Wayland protocol only)
- System tray icon (stretch goal, not required)
