# Spec 001: VSCode Launcher

**Status: COMPLETE** (superseded in part by [spec 002](002-recents-integration.md) — the manually-managed workspace list was replaced with a live view of VSCode's own Recent history. Tmux plumbing and window placement are unchanged.)

## Description

`vscode-launcher` is a PyQt6 GUI for bulk-launching VSCode workspaces on CachyOS / KDE Plasma 6 (Wayland). Each launch:

1. Opens the workspace in a new VSCode window
2. Moves the window to the primary monitor (Philips) and maximizes it — VSCode otherwise opens at a small default size
3. Plumbs a signal to the window's integrated terminal so its tmux client switches to the project's named tmux session

The tool addresses three pain points: VSCode starts with a small window every time, each workspace has to be opened manually, and the shared system-wide tmux server requires manual `switch-client` to the correct session after each launch.

## Goals

- Eliminate repetitive manual steps when resuming work on multiple projects
- Preserve the existing shared tmux server — do NOT kill or create sessions from the launcher
- Provide a user-editable mapping between VSCode workspaces and pre-existing tmux session names
- Reuse `vscode-gather` (sibling sub-project) for window placement instead of reimplementing KWin scripting

## Non-Goals

- Managing tmux session lifecycle (creating, killing, renaming sessions)
- Reading VSCode's internal state databases (`state.vscdb`, `storage.json`) — workspace list is launcher-managed
- Supporting X11 / non-KDE window managers
- Remote / SSH workspaces (local folders only)

## Requirements

### GUI (PyQt6)

- Main window: scrollable list of saved workspace entries
- Each row displays: workspace label, workspace path (folder or `.code-workspace` file), mapped tmux session name, checkbox for bulk-select
- Toolbar / buttons:
  - **Launch Selected** — launches all checked entries in parallel, then calls `vscode-gather` once at the end
  - **Launch All**
  - **Add Workspace** — file picker for a folder or `.code-workspace` file; prompts for a friendly label and a tmux session name (dropdown populated from `tmux list-sessions -F '#S'`, plus free-text fallback)
  - **Edit** (on selected row) — change label, path, or tmux session mapping
  - **Remove** (on selected row) — with confirmation
  - **Reorder** — drag-and-drop or up/down buttons
- Window geometry persists across restarts
- System tray: optional, out of scope for v1

### Workspace Source

- Launcher maintains its own list (primary source of truth) in `~/.config/vscode-launcher/workspaces.json`
- **Optional v1.1**: "Import from VSCode recents" button that parses `~/.config/Code/User/globalStorage/storage.json`. Deferred unless trivial during implementation.

### VSCode Launch

- For each selected entry, spawn `code <workspace-path>` as a detached subprocess
- Pass `VSCODE_LAUNCHER_TMUX_SESSION=<session-name>` in the child process environment so the integrated-terminal shell hook (see Tmux Plumbing) can read it
- Wait briefly (~1–2 s) after spawning to let windows register with KWin, then invoke `vscode-gather`

### Window Placement

- Delegate to `vscode-gather` (sibling script, already installed to `~/bin/vscode-gather`)
- Launcher invokes `vscode-gather` as a subprocess after launching all selected workspaces
- `vscode-gather` auto-detects the primary monitor and maximizes all VSCode windows on it
- No KWin scripting code is duplicated in the launcher

### Tmux Plumbing

The shared system-wide tmux server must NOT be disturbed. The launcher only needs to cause the VSCode window's integrated terminal to attach to (or switch to) the correct pre-existing session.

**Mechanism (chosen approach)**:

1. Launcher sets `VSCODE_LAUNCHER_TMUX_SESSION=<session-name>` in the environment of the `code` subprocess it spawns. VSCode inherits this env for its integrated terminals.
2. A small shell snippet (installed into the user's `~/.zshrc` by `install.sh`) runs on shell startup:

   ```zsh
   # --- vscode-launcher tmux hook (BEGIN) ---
   if [[ -n "${VSCODE_LAUNCHER_TMUX_SESSION:-}" ]]; then
     if [[ -z "${TMUX:-}" ]]; then
       # Not yet in tmux: attach directly to the target session
       tmux attach -t "$VSCODE_LAUNCHER_TMUX_SESSION" 2>/dev/null && return
     else
       # Already in tmux (second terminal in same window): switch client
       tmux switch-client -t "$VSCODE_LAUNCHER_TMUX_SESSION" 2>/dev/null
     fi
   fi
   # --- vscode-launcher tmux hook (END) ---
   ```

3. Hook is idempotent and bounded by the BEGIN/END markers so `install.sh` and `uninstall.sh` can add/remove it cleanly.
4. If the target session does not exist, the hook exits silently; user sees a normal shell. The launcher does NOT create sessions.

**Session discovery in the GUI**:

- "Add Workspace" and "Edit" dialogs query `tmux list-sessions -F '#S'` and present a dropdown. Free-text input is permitted (so users can pre-configure a session name that will exist later).
- A "Refresh sessions" button in the dialog re-queries.

### Mapping Configuration

- Stored in `~/.config/vscode-launcher/workspaces.json`:

  ```json
  {
    "version": 1,
    "workspaces": [
      {
        "id": "uuid-or-stable-hash",
        "label": "platform-backend",
        "path": "/home/user/git/platform-backend",
        "tmux_session": "platform-backend"
      }
    ],
    "window_geometry": {"x": 100, "y": 100, "w": 600, "h": 400}
  }
  ```

- Editable from the GUI; file is human-readable for manual edits
- Unknown keys preserved on round-trip (future-compatibility)

### Platform

- Target: CachyOS / KDE Plasma 6 (Wayland)
- Python: system `/usr/bin/python3`, PyQt6
- Requires: `tmux`, `code` (VSCode CLI), `vscode-gather` (sibling script)

## Acceptance Criteria

- [x] Application launches as a PyQt6 window showing a list of saved workspaces
- [x] User can add a new workspace entry via folder / file picker, with a friendly label
- [x] "Add" and "Edit" dialogs populate a tmux session dropdown from `tmux list-sessions -F '#S'`, with free-text fallback and a refresh button
- [x] User can edit any field of an existing entry (label, path, tmux session)
- [x] User can remove an entry (with confirmation)
- [x] User can reorder entries (drag-and-drop or up/down buttons)
- [x] User can multi-select entries via checkboxes and press "Launch Selected" to launch all selected workspaces
- [x] "Launch All" launches every saved workspace
- [x] Each launch spawns `code <path>` with `VSCODE_LAUNCHER_TMUX_SESSION=<session>` set in the child environment
- [x] After launching, `vscode-gather` is invoked exactly once to move and maximize the new windows on the primary monitor
- [x] `install.sh` installs the zsh shell hook between clearly marked BEGIN/END markers in `~/.zshrc` (idempotent)
- [x] `uninstall.sh` removes the shell hook block cleanly, plus the desktop entry and symlink
- [x] Shell hook: opening a VSCode integrated terminal with `VSCODE_LAUNCHER_TMUX_SESSION=foo` set causes the terminal to attach to (or switch-client to) tmux session `foo`
- [x] Shell hook: if the target tmux session does not exist, the shell starts normally without error
- [x] The launcher never creates, kills, or renames tmux sessions
- [x] Config stored at `~/.config/vscode-launcher/workspaces.json`; window geometry persists across restarts
- [x] Config file is human-readable JSON and tolerates unknown keys
- [x] Missing dependencies (`tmux`, `code`, `vscode-gather`) produce a clear error message, not a stack trace
- [x] README.md documents features, installation, usage, config, and the zsh-hook mechanism
- [x] Tests exist and pass (`pytest`), covering: config load/save, tmux session discovery parsing, launch command assembly
- [x] `install.sh` creates a `.desktop` entry and a symlink (e.g. `~/bin/vscode-launcher`)
- [x] `uninstall.sh` removes all installed files including the zsh-hook block

## Architecture

### File Structure

```
vscode-launcher/
├── README.md
├── install.sh
├── uninstall.sh
├── vscode_launcher.py              # Main PyQt6 app
├── tmux_hook.zsh                   # Shell snippet copied by install.sh
├── vscode-launcher.desktop
├── specs/
│   └── 001-vscode-launcher.md
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   └── test_unit_vscode_launcher.py
└── validation-reports/
```

### Key Components

- **ConfigManager** — load/save `workspaces.json`, preserve unknown keys
- **Workspace (dataclass)** — `id`, `label`, `path`, `tmux_session`
- **TmuxClient** — thin wrapper: `list_sessions()` → `List[str]` via `tmux list-sessions -F '#S'`
- **Launcher** — `launch(workspaces)`: spawns `code <path>` subprocesses with env var set, then calls `vscode-gather` once via subprocess
- **WorkspaceRowWidget** — single row with checkbox, label, path, tmux-session indicator, edit/remove buttons
- **WorkspaceListWidget** — scrollable list; supports reordering and multi-select
- **AddEditDialog** — folder picker + tmux-session dropdown + label input
- **MainWindow** — QMainWindow wrapping the list widget plus toolbar

### Shell Hook Install Strategy

`install.sh` uses a sentinel-based block insertion to be idempotent:

1. If the block `--- vscode-launcher tmux hook (BEGIN) --- ... (END)` already exists in `~/.zshrc`, skip.
2. Otherwise, append the contents of `tmux_hook.zsh` to `~/.zshrc`.

`uninstall.sh` removes the block between markers (inclusive) using `sed` with a file backup.

## Design Decisions (carried forward from pre-spec discussion)

1. **Workspace source**: user-managed list. VSCode history import deferred.
2. **Tmux switch mechanism**: env-var-plus-shell-hook. Preferred over manual helper scripts because it runs automatically every time the VSCode integrated terminal starts, and it degrades gracefully (does nothing if the env var is absent or the session is missing).
3. **Window placement**: delegate entirely to `vscode-gather`. All VSCode windows — launcher-spawned or not — will end up on the Philips monitor. User explicitly accepted this behavior.
4. **Maximize**, not fullscreen: KWin's `setMaximize(true, true)` via `vscode-gather` already does this.
5. **GUI framework**: PyQt6, consistent with `foghorn-leghorn`, `peripheral-battery-monitor`, `dhcp-lease-monitor`.
6. **Bulk launch**: multi-select via checkboxes; `vscode-gather` is invoked once after all spawns, not per-window.

## Open Questions (to resolve during implementation)

- **Env var lifetime**: does VSCode propagate the launcher's env to integrated terminals when the workspace is opened in a *new window* (vs. reusing an existing window)? If VSCode reuses a running instance, the env var from the new `code` invocation may not propagate. Mitigation: force a new window with `code --new-window <path>` (aka `-n`). This should be the default launch flag.
- **Launch timing**: how long to wait after spawning `code` before calling `vscode-gather`? Too short and windows aren't registered yet; too long and the UI feels sluggish. Start with 1500 ms and tune.
- **Shell hook scope**: this spec targets zsh only (per user's setup). If bash support is needed later, a parallel hook can be added to `install.sh`.

## Implementation Notes

- Use `subprocess.Popen` with `start_new_session=True` for spawning `code` so launcher exit doesn't kill VSCode
- Use `code --new-window` to force a fresh window per invocation (prevents folder-adding to existing window and env-var non-propagation)
- `vscode-gather` invocation: `subprocess.run(["vscode-gather"], check=False)` — failure to place windows should not be fatal
- Tmux session parsing: `tmux list-sessions -F '#S'` produces one session name per line; handle the "no server running" exit code 1 gracefully (return empty list)
- Config migration: use a top-level `"version": 1` field so future format changes can be detected
