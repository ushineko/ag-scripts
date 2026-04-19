# Spec 002: VSCode Recents Integration

**Status: COMPLETE**

## Description

Replaces the manually-managed workspace list from [spec 001](001-vscode-launcher.md) with a list sourced directly from VSCode's own "Recent" history, read from its SQLite state database (`~/.config/Code/User/globalStorage/state.vscdb`, key `history.recentlyOpenedPathsList`).

Rationale: after the v1.0 implementation landed, the user expected the launcher's list to mirror VSCode's own startup "Recent" view rather than requiring each workspace to be added by hand. The tool's unique value is the tmux-session plumbing and window placement — workspace tracking is already solved by VSCode itself.

## Goals

- List = VSCode Recent workspaces, in VSCode's order (most-recent first)
- Launcher-specific overlay state (tmux session mapping per path, hidden paths) persists in our own config
- No duplication of workspace tracking — if VSCode doesn't know about it, it doesn't appear
- Preserve the core value: bulk launch, vscode-gather integration, zsh tmux hook
- Migrate v1 config automatically (don't lose user's tmux session mappings)

## Non-Goals

- Writing to VSCode's state DB (read-only)
- Managing VSCode's recent list (pinning, removing-from-VSCode-history)
- Discovering workspaces outside VSCode's recent list

## Requirements

### VSCode Recents Reader

- Read `~/.config/Code/User/globalStorage/state.vscdb` in read-only mode (`sqlite3.connect("file:...?mode=ro", uri=True)`) so the DB can be accessed even while VSCode is running
- Query: `SELECT value FROM ItemTable WHERE key = 'history.recentlyOpenedPathsList'`
- Parse the JSON value; `entries` is a list of either:
  - `{"folderUri": "file://<path>"}` — a plain folder workspace
  - `{"workspace": {"configPath": "file://<path>"}}` — a multi-root `.code-workspace` file
- Convert `file://` URIs to local paths via `urllib.parse.urlparse` + `unquote`
- Skip entries whose scheme is not `file://` (e.g., `vscode-vfs://github/...` remote workspaces)
- Return an empty list on any error (missing file, SQLite error, bad JSON)
- Preserve VSCode's ordering

### Label Conventions

- Folder workspace: `<basename>` (e.g. `ag-scripts`)
- `.code-workspace` file: `<stem> (Workspace)` (e.g. `platform-backend (Workspace)`) — matches VSCode's own labeling

### Config Schema (v2)

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

- `tmux_mappings`: path → tmux session name. Empty string / missing = no mapping (blank "tmux" column in UI, no env var set at launch).
- `hidden_paths`: paths to filter out of the displayed list (VSCode's recent list still contains them; we just don't show them).
- Unknown top-level keys preserved on save.

### Config Migration (v1 → v2)

- Detect v1 by `"version": 1` in the config file
- For each entry in v1 `workspaces`: if both `path` and `tmux_session` are non-empty, add to v2 `tmux_mappings`
- Drop the v1 `workspaces` key
- Write back at v2 on next save
- Test coverage: `TestConfigManager.test_v1_migration` exercises this path

### GUI Changes

- **Removed**: Add Workspace, Edit, Remove buttons; drag-and-drop reorder; `id` field on Workspace
- **Added**:
  - **Refresh** — re-read VSCode state DB and rebuild the list
  - **Set Tmux Session…** — opens `TmuxSessionDialog` for the currently selected row; writes to `tmux_mappings`
  - **Hide** — adds current path to `hidden_paths`
  - **Unhide All** — clears `hidden_paths`
- Double-click a row → Set Tmux Session dialog
- Context menu: Launch, Set Tmux Session…, Hide
- Empty-state messages differ by cause (DB missing / all hidden / no recents in VSCode)

### TmuxSessionDialog

- Shows the workspace label at the top for context
- Editable dropdown populated from `tmux list-sessions -F '#S'` with Refresh button
- Blank session clears the mapping
- Hint text clarifies the launcher never creates/kills sessions

## Acceptance Criteria

- [x] `VSCodeRecentsReader` reads `state.vscdb` in read-only mode and returns one `Workspace` per entry
- [x] Folder URIs produce `Workspace(label=<basename>, is_workspace_file=False)`
- [x] `.code-workspace` config paths produce `Workspace(label="<stem> (Workspace)", is_workspace_file=True)`
- [x] Non-`file://` URIs (e.g. `vscode-vfs://`) are skipped
- [x] Missing DB, SQLite errors, and bad JSON all return an empty list instead of raising
- [x] Order from VSCode is preserved
- [x] Config schema v2 stores `tmux_mappings` (path → session) and `hidden_paths`
- [x] v1 config is detected and migrated on load; `workspaces` list is dropped; valid `path`/`tmux_session` pairs flow into `tmux_mappings`
- [x] Unknown top-level config keys are preserved on round-trip
- [x] Main window shows VSCode recents on launch, with per-path tmux mapping applied when present
- [x] Refresh button re-reads the DB and rebuilds the list
- [x] "Set Tmux Session…" dialog writes the session name to `tmux_mappings[path]` (or removes the key when blank)
- [x] Hide adds the path to `hidden_paths` and removes the row from view; Unhide All clears it
- [x] Double-click a row opens the Set Tmux Session dialog
- [x] Launch Selected / Launch All still work; each launch carries `VSCODE_LAUNCHER_TMUX_SESSION` when a mapping exists
- [x] `vscode-gather` is invoked exactly once after a bulk launch
- [x] Empty state shows a specific message based on cause (missing DB vs. all hidden vs. no recents)
- [x] Tests exist and pass (`pytest`), covering the reader, v1→v2 migration, config round-trip, and the MainWindow integration with mocked recents

## Architecture

### New module pieces

- `VSCodeRecentsReader` — wraps the SQLite read + URI parsing
- `uri_to_path(uri)`, `label_for_path(path, is_workspace_file)` — pure helpers (easily unit-tested)
- `TmuxSessionDialog` — replaces the old `AddEditDialog`; only handles the tmux session field

### Removed pieces

- `Workspace.id`, `Workspace.to_dict`, `Workspace.from_dict` — no longer round-tripped through config
- `ConfigManager.parse_workspaces` — list of stored workspaces no longer exists
- `WorkspaceListWidget.iter_workspace_ids` — list is keyed by path now; reorder removed
- Add / Edit / Remove toolbar actions

## Open Questions (deferred)

- **Other VSCode distributions** (Code - Insiders, Code - OSS, VSCodium). The default DB path is hardcoded to `~/.config/Code/User/globalStorage/state.vscdb`. If users need to target a different distribution, a CLI flag or env var could select the DB path. Deferred until there's a concrete need.
- **Remote workspaces** (`vscode-vfs://`, SSH). Currently filtered out. Supporting them would require telling VSCode how to re-open them via the `code` CLI, which varies by scheme. Deferred.
- **Pre-existing v1 config migrations in the wild** — the user only had a fresh install with no workspaces saved when the redesign happened, so the migration path was tested synthetically, not against real user data.
