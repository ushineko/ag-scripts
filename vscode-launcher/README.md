# vscode-launcher

Bulk-launch VSCode workspaces directly from VSCode's own **Recent** list, with automatic window placement and tmux session switching. Targets CachyOS / KDE Plasma 6 (Wayland).

Solves three recurring pain points:

- VSCode opens at a small default size every time — this tool maximizes it on the primary monitor
- Each workspace has to be opened manually — this tool launches any number at once
- A shared system-wide tmux server needs a manual `switch-client` after each launch — this tool wires the integrated terminal to the correct session automatically

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [How It Works](#how-it-works)
- [Configuration](#configuration)
- [Uninstallation](#uninstallation)
- [Changelog](#changelog)

## Features

- Reads your workspace list live from VSCode's own Recent history — nothing to maintain by hand
- **Shows which workspaces are currently open**, with running ones sorted to the top and a `● running` badge — prompts before double-launching
- **Per-row Start / Stop / Activate buttons**: Start (non-running) launches the workspace; Activate (running) raises and focuses its VSCode window; Stop (running) closes the window via KWin while leaving the main VSCode process alive
- PyQt6 GUI with multi-select checkboxes; bulk-launch with one click
- Per-workspace tmux-session mapping, editable via a dropdown populated from `tmux list-sessions`
- Hide / Unhide workspaces you don't want cluttering the launcher
- Delegates window placement to the sibling [`vscode-gather`](../vscode-gather) tool — each launched window is moved to the primary monitor and maximized
- Installs a small zsh hook into `~/.zshrc` so the VSCode integrated terminal attaches to (or switches to) the correct pre-existing tmux session automatically
- Never creates, kills, or renames tmux sessions — the shared system tmux server is left alone

## Requirements

- KDE Plasma 6 (Wayland)
- Python 3 with PyQt6
- VSCode (reads `~/.config/Code/User/globalStorage/state.vscdb`)
- `code` (VSCode CLI) on `PATH`
- `tmux` (optional — only needed for session switching)
- `vscode-gather` (optional — only needed for auto-placement / maximize)
- zsh (the shell hook targets zsh; bash support could be added later)

## Installation

```bash
./install.sh
```

This:

1. Symlinks `vscode_launcher.py` to `~/.local/bin/vscode-launcher`
2. Installs a `.desktop` entry so it shows up in KRunner and the app menu
3. Appends the tmux shell hook into `~/.zshrc` (idempotent, bounded by markers)

Open a new zsh session (or `exec zsh`) for the hook to take effect.

## Usage

Launch the GUI:

```bash
vscode-launcher
```

The list is populated from VSCode's Recent workspaces. Folders show as `<folder-name>`; multi-root workspace files show as `<stem> (Workspace)` — matching VSCode's own labeling.

### Assigning a tmux session to a workspace

1. Click a row to select it
2. Click **Set Tmux Session…** (or double-click the row)
3. Pick an existing tmux session from the dropdown, or type a new name (the launcher never creates it — you configure an existing shared session)
4. Click **OK**

The mapping is saved to `~/.config/vscode-launcher/workspaces.json` and keyed by workspace path.

To remove a mapping: open the dialog and clear the field.

### Bulk-launching

1. Tick the checkboxes next to the workspaces you want to launch
2. Click **Launch Selected**

Each ticked workspace opens in a new VSCode window; about 1.5 seconds later `vscode-gather` runs once and moves/maximizes all VSCode windows on the primary monitor. Open an integrated terminal in any launched window — the zsh hook attaches it to the tmux session you configured for that workspace.

**Launch All** ignores the checkboxes and launches every visible (non-hidden) workspace.

### Hiding workspaces

VSCode keeps every workspace you've ever touched in its Recent list. To declutter the launcher:

- Select a row and click **Hide** — it is filtered out of the launcher list (VSCode's own Recent list is unaffected)
- Click **Unhide All** to restore all hidden entries

### Refreshing

Click **Refresh** to re-read VSCode's state DB AND re-scan which VSCode windows are currently open — useful after you've opened or closed a workspace in VSCode and want the launcher to reflect the new state without restarting.

### Running workspaces

Each row shows a green `● running` badge when the workspace is already open in a VSCode window. Running workspaces sort ahead of the rest, and within each group (running / not running) MRU order from VSCode's Recent list is preserved.

If you tick a running workspace and click Launch Selected (or Launch All while any are running), you get a 3-button prompt: **Launch Anyway** (accepts the duplicate), **Skip Running** (launches only the ones that aren't open), or **Cancel**. Detection uses KWin scripting via D-Bus — the same mechanism the sibling `vscode-gather` tool uses — and silently degrades (no badges, no prompt) if `qdbus6` or `journalctl` aren't available.

### Per-row actions

Each row has contextual buttons on the right:

- **Start** (non-running rows) — launches that single workspace (same flow as Launch Selected for one entry)
- **Activate** (running rows) — raises and focuses the existing VSCode window via KWin `workspace.activeWindow = w`
- **Stop** (running rows) — closes the VSCode window via KWin `w.closeWindow()`. VSCode's own "unsaved changes?" dialog still appears if applicable; Stop does not bypass it. The VSCode main process is not killed — other windows stay open.

Stop does not auto-refresh the list because an unsaved-changes prompt may stall the close. Click **Refresh** once you've resolved any save prompt to see updated running state.

## How It Works

### Workspace source

The launcher opens `~/.config/Code/User/globalStorage/state.vscdb` in SQLite read-only mode (`mode=ro`, so it works even while VSCode is running) and queries:

```sql
SELECT value FROM ItemTable WHERE key = 'history.recentlyOpenedPathsList';
```

The value is JSON — each entry is either `{"folderUri": "file://..."}` (a folder) or `{"workspace": {"configPath": "file://..."}}` (a `.code-workspace` file). Non-`file://` URIs (e.g., `vscode-vfs://github/...` remote workspaces) are skipped.

### VSCode launch

For each selected workspace, the launcher spawns:

```bash
code --new-window <workspace-path>
```

as a detached subprocess, with `VSCODE_LAUNCHER_TMUX_SESSION=<session-name>` set in the child's environment (when a mapping exists). `--new-window` is required — otherwise VSCode may reuse an existing window and the env var will not propagate to its integrated terminals.

### Window placement

After all workspaces have been spawned, the launcher waits 1.5 s (so windows register with KWin) then runs `vscode-gather`, which uses KWin scripting via D-Bus to move every VSCode window to the primary monitor and maximize it. The launcher never talks to KWin directly.

### Tmux switching

The zsh hook installed into `~/.zshrc` runs on every shell startup. When it detects it's inside a VSCode integrated terminal (`TERM_PROGRAM=vscode`), it calls a small Python helper `vscl-tmux-lookup "$PWD"` that:

1. Walks up from `$PWD` looking for the longest ancestor path present in `tmux_mappings`
2. If nothing matches directly, scans any `.code-workspace` file keyed in `tmux_mappings`, resolves its `folders[]` array (absolute + relative paths), and checks whether `$PWD` is inside one of those folders

If the lookup returns a session name:

- Outside tmux: `tmux attach -t <session>` attaches the shell to it
- Inside tmux: `tmux switch-client -t <session>` switches the current client
- Missing session or no match: silent no-op — shell starts normally

This PWD-based lookup is used instead of environment-variable propagation because `code --new-window <path>` signals an already-running VSCode process rather than spawning a fresh one, so env vars set by the launcher don't reach the integrated terminal when VSCode is already open.

The hook never creates sessions.

## Configuration

Stored at `~/.config/vscode-launcher/workspaces.json`:

```json
{
  "version": 2,
  "tmux_mappings": {
    "/home/user/git/ag-scripts": "ag-scripts",
    "/home/user/vscode-workspaces/platform-backend.code-workspace": "platform-backend"
  },
  "hidden_paths": [
    "/home/user/git/some-old-project"
  ],
  "window_geometry": {"x": 100, "y": 100, "w": 700, "h": 500}
}
```

- `tmux_mappings` — path → tmux session name (empty / missing = no mapping)
- `hidden_paths` — paths to filter out of the launcher view (VSCode's own Recent list is never modified)
- Unknown top-level keys are preserved on save for forward compatibility

The file is human-readable and safe to edit manually.

### Migrating from v1.0

If you used v1.0 (manual workspace list), the first run of v1.1 automatically:

- Preserves any `tmux_session` mappings from your v1 `workspaces` list as `tmux_mappings`
- Drops the `workspaces` list (VSCode is the source of truth now)
- Writes back the config at `"version": 2`

## Uninstallation

```bash
./uninstall.sh
```

Removes the symlink, the `.desktop` entry, and the zsh hook block from `~/.zshrc` (a backup is written to `~/.zshrc.vscode-launcher.bak`). You are prompted before the config directory is deleted.

## Changelog

### v1.4

- New: per-row **Start** (non-running) / **Stop** + **Activate** (running) buttons. Activate raises and focuses the matching VSCode window via KWin `workspace.activeWindow = w`; Stop closes the window via `w.closeWindow()` without killing the shared VSCode main process. Labels are JSON-encoded when injected into the KWin JS source.
- UX: the list widget now uses `ClickFocus`, so no row is highlighted on startup — a row only lights up when the user actively clicks it.

### v1.3

- New: running-workspace detection. The launcher enumerates VSCode windows via KWin scripting, marks each already-open workspace with a `● running` badge, and sorts running ones to the top. MRU order from VSCode's Recent list is preserved within each group (running then non-running, both MRU-ordered).
- New: launching a workspace that is already open now shows a 3-button prompt (Launch Anyway / Skip Running / Cancel) instead of silently producing a duplicate VSCode window.
- Feature degrades silently when `qdbus6` or `journalctl` are unavailable (no badges, no prompt).

### v1.2

- Fixed: tmux switching now works when VSCode is already running. Replaced the brittle `VSCODE_LAUNCHER_TMUX_SESSION` env-var path — which didn't survive `code --new-window` signaling an existing VSCode process — with a PWD-based lookup performed by a new helper, `vscl-tmux-lookup`.
- New: `.code-workspace` files now resolve correctly. The lookup helper parses the `folders[]` array inside the workspace file (with relative-path resolution) and matches the terminal's `$PWD` against any listed folder.
- `vscl-tmux-lookup` is installed as a sibling symlink in `~/.local/bin`.

### v1.1

- List is now sourced from VSCode's own Recent history (`state.vscdb`), not a manually-managed list
- New: **Refresh**, **Set Tmux Session…**, **Hide**, **Unhide All** toolbar actions
- New: double-click a row to set its tmux session
- Removed: Add Workspace / Edit / Remove (VSCode is the source of truth)
- Config schema v2 with automatic migration from v1

### v1.0

- Initial release
- PyQt6 GUI with bulk-launch, add/edit/remove, drag-and-drop reordering
- Tmux session dropdown populated from `tmux list-sessions`
- Zsh hook for automatic tmux attach / switch-client in the VSCode integrated terminal
- Delegates window placement to sibling `vscode-gather`
