# Spec 006: Grid Layout + Status Column

**Status: COMPLETE**

## Description

Replaces the single-column list of workspaces (stacked label / path / tmux / badge / buttons inside one row widget) with a proper 5-column grid. Each piece of information gets its own column so values line up vertically and the UI scales cleanly as content changes.

The running state, previously an inline `● running` badge next to the label, becomes its own **Status** column. The checkbox on running rows is disabled — you can't bulk-launch something that is already open — which makes the old 3-button "Already running" dialog unnecessary, so it's removed.

## Goals

- Columns align vertically so scanning the list is fast
- "Is this open?" is answered by a dedicated column, not a badge squeezed next to the label
- The UI tells the truth about what bulk-launch can do: if a row's checkbox is disabled, you know it's running
- Simplify the launch flow: drop the mid-flow 3-button dialog

## Non-Goals

- Column resize UI / user-configurable widths — column widths are fixed; not worth the complexity for a personal tool
- Column headers — omitted (column purposes are self-evident from content; headers visually dominate for a 12-row list)
- Sort-by-column controls — sort order is dictated by running-status and MRU (spec 004); there's no manual sort mode

## Requirements

### Layout

- `QTableWidget` with 5 columns, no vertical or horizontal headers, grid-lines off
- Single selection, row-selection behavior, edit triggers disabled
- Focus policy `ClickFocus` (preserved from v1.4 — nothing highlighted on startup)
- Fixed column widths:
  - Column 0 (checkbox): 40 px
  - Column 1 (workspace): stretch
  - Column 2 (status): 90 px
  - Column 3 (tmux): 160 px
  - Column 4 (actions): 180 px
- Row height: 54 px (fits two text lines in the Workspace column)

### Cell contents

- **Checkbox**: plain `QCheckBox` centered in its cell; `setEnabled(False)` when `workspace.is_running`
- **Workspace**: `QLabel` with rich text — `<b>label</b>` on line 1, `<small style="color:gray">path</small>` on line 2
- **Status**: `QLabel`, center-aligned, `<span style="color:#4caf50">● running</span>` when running; blank otherwise
- **Tmux**: `QLabel` with the session name or `—`
- **Actions**: `QWidget` container laying out `[Activate][Stop]` (running) or `[Start]` (non-running) horizontally; all buttons use `Qt.FocusPolicy.NoFocus` (preserved from v1.4)

### Behavior changes

- **Bulk launch (`Launch Selected` / `Launch All`)** silently skips any target whose `is_running` flag is true. This is the layer-two defense. The disabled checkbox on running rows is the primary UX signal.
- **Per-row `Start`** only renders on non-running rows; pressing it always launches (`allow_running=True`) because the UI contract would be broken if it silently did nothing.
- **Context-menu `Launch`** forces `allow_running=True`. This is the power-user manual override for deliberately duplicating a window.
- **Removed**: `_launch_paths`'s 3-button "Already running" dialog. The launch flow is now straight-line: validate `code` is installed, filter or not based on `allow_running`, spawn, schedule `vscode-gather`.

### Signals

`WorkspaceTableWidget` exposes the same three `pyqtSignal(str)` signals as v1.4's `WorkspaceListWidget` — `start_requested`, `stop_requested`, `activate_requested` — so the wiring in `MainWindow._build_ui` doesn't change beyond the widget constructor. `cellDoubleClicked(row, col)` replaces the old `itemDoubleClicked` for the "open Set Tmux Session dialog" shortcut.

### Selection helpers

- `path_at_row(row: int) -> str | None` replaces `item(i).data(UserRole)`
- `checked_workspace_paths()` — same interface as before, now scanning column 0 cell widgets
- `all_workspace_paths()` — same interface
- `clear_workspaces()` replaces `clear()`. Also wipes the path-by-row map so stale references don't leak.

## Acceptance Criteria

- [x] `WorkspaceTableWidget` has 5 columns with fixed widths except for the workspace column which stretches
- [x] Checkbox is disabled on running rows and enabled on non-running rows
- [x] Running rows have `[Activate][Stop]` in the Actions column; non-running rows have `[Start]`
- [x] Status column shows `● running` (green) when `is_running` and is blank otherwise
- [x] Workspace column shows the label bold on line 1 and the path in small gray text on line 2
- [x] Tmux column shows the session name or `—`
- [x] `_launch_paths(..., allow_running=False)` (default) skips running workspaces
- [x] `_launch_paths(..., allow_running=True)` launches running workspaces (duplicate window)
- [x] Context-menu `Launch` action uses `allow_running=True`
- [x] The old 3-button "Already running" dialog is gone (grep for `Launch Anyway` returns nothing)
- [x] Double-click any cell opens the Set Tmux Session dialog
- [x] `MainWindow.list_widget.rowCount()` reflects the workspace count (replaces `count()` asserts in tests)
- [x] Startup still shows no highlighted row (Qt focus policy preserved)
- [x] All previous v1.4 behavior (Activate / Stop / Start handlers, running-first MRU sort, running badge color) is preserved

## Architecture

### Renamed / removed

- `WorkspaceListWidget` → `WorkspaceTableWidget`
- `_build_row_widget` → split into five `_build_*_cell` helpers (one per column)
- Removed: `AddEditDialog` was already gone in v1.1; no resurgence here
- Removed from `vscode_launcher.py` imports: `QListWidget`, `QListWidgetItem`
- Added to imports: `QHeaderView`, `QTableWidget`

### Launch flow simplification

- `_launch_paths(paths, allow_running=False)` — single filter decision at the top of the method; the old prompt-box + `clickedButton()` branching is gone
- `_launch_current(allow_running=True)` — context-menu default
- `_on_start_requested(path)` — always allow_running=True since the Start button only shows on non-running rows anyway (this is an explicit intent signal for readability)

## Implementation Notes

- `setCellWidget` is used for every cell. An alternative would have been `QTableWidgetItem` for the plain-text cells, but mixing widget and item cells complicates `cellWidget`-based test lookups. Uniform `setCellWidget` is simpler and the performance cost is negligible for a ~12-row list.
- `header.setSectionResizeMode(col, Fixed)` + `setColumnWidth` for the four fixed columns; `Stretch` for the workspace column. Row height is set per row via `setRowHeight`.
- `cellDoubleClicked(row, col)` signal fires on any cell, which is desired — users shouldn't have to aim at the label specifically to open the tmux dialog.
- `rowAt(pos.y())` is the QTableWidget equivalent of `itemAt(pos)` for context-menu lookup.
- The bundled v1.4 icon, zsh hook, and `vscl-tmux-lookup` helper are unchanged.

## Alternatives Considered

- **Column headers** — evaluated; rejected. Headers add vertical space and visual weight for a personal-use list whose columns are obvious ("that's the checkbox column, that's the tmux column"). Worth revisiting if this grows into a bigger table.
- **Replace `QTableWidget` with `QTreeView` + custom `QAbstractTableModel`** — cleaner MVC, but ~3× the code for a read-mostly view with thirteen rows. Deferred.
- **Keep the 3-button launch dialog as a power-user feature** — rejected. The dialog duplicated the affordance the context-menu `Launch` already provides; removing it is net simpler.
- **Disable the entire row (including Activate / Stop) when running instead of just the checkbox** — rejected. Activate and Stop are the primary actions for running rows; disabling them would defeat the purpose of showing the controls.
