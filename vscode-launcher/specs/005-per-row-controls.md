# Spec 005: Per-Row Start / Stop / Activate Controls

**Status: COMPLETE**

## Description

Each row in the launcher gains contextual action buttons:

- Running rows: **Activate** (bring the VSCode window to the front) and **Stop** (close the VSCode window)
- Non-running rows: **Start** (same as launching that workspace)

The buttons make routine operations one-click instead of requiring the user to Alt-Tab, find the window, or tick-and-Launch for a single entry.

## Goals

- Stop a workspace's VSCode window without killing the shared VSCode main process (other windows untouched)
- Activate / raise a running workspace's window
- Start a single workspace without going through the checkbox + bulk-launch flow
- Keep the VSCode main process untouched — close a *window*, not the binary

## Non-Goals

- Bulk stop / bulk activate (skip until demand)
- Forcing closes past VSCode's own "unsaved changes?" dialog. The normal close flow is triggered, which respects unsaved state.
- Listening for KWin window-closed events to auto-refresh the row — skipped to keep the implementation simple and avoid lying to the user about state that's still being confirmed (save prompts, etc.)

## Requirements

### Window actions via KWin scripting

- New `WindowScanner.perform_window_action(label, action)` method; `action` in `{"close", "activate"}`
- `close` → KWin `w.closeWindow()` on the first matching window
- `activate` → KWin `workspace.activeWindow = w` on the first matching window
- Matching uses the same token-split rule as running detection (see spec 004), so `aiq-ralph` does not match `aiq-ralphbox`
- Label is **JSON-encoded** when injected into the JS source (defense in depth — prevents any label containing quotes / backslashes / newlines from breaking out of the JS string literal)
- Returns `True` when the compositor log shows a `VSCL_ACTION_OK:` marker, `False` otherwise
- Silent return `False` on any failure (tooling missing, no matching window, KWin error)

### Per-row buttons

- `WorkspaceListWidget` emits three `pyqtSignal(str)` (path) signals: `start_requested`, `stop_requested`, `activate_requested`
- Row widget layout depends on `workspace.is_running`:
  - Running: `[checkbox] [label block]   [Activate] [Stop]`
  - Not running: `[checkbox] [label block]   [Start]`
- Buttons have `Qt.FocusPolicy.NoFocus` so clicking them doesn't steal keyboard focus onto the list (preserving the "nothing highlighted by default" behavior from the previous UX fix)

### Handlers in `MainWindow`

- `_on_start_requested(path)` → `_launch_paths([path])`, which reuses the existing `code --new-window` + delayed `vscode-gather` flow
- `_on_stop_requested(path)` → `window_scanner.perform_window_action(label, "close")`
- `_on_activate_requested(path)` → `window_scanner.perform_window_action(label, "activate")`
- No auto-refresh after Stop — VSCode's "unsaved changes?" prompt may stall the close; polling right after would lie about state. User hits Refresh when ready.

## Acceptance Criteria

- [x] Running rows render `[Activate]` and `[Stop]` buttons; non-running rows render `[Start]`
- [x] Buttons have `NoFocus` focus policy so clicking doesn't move keyboard focus into the list widget
- [x] `WorkspaceListWidget` exposes `start_requested`, `stop_requested`, `activate_requested` signals carrying the workspace path
- [x] `WindowScanner.perform_window_action(label, "close")` closes the matching VSCode window via `w.closeWindow()`
- [x] `WindowScanner.perform_window_action(label, "activate")` raises + focuses the matching VSCode window via `workspace.activeWindow = w`
- [x] Unknown action names raise `ValueError`
- [x] Labels containing quotes / backslashes / newlines are JSON-encoded in the JS script source, preventing any JS string-literal escape
- [x] `perform_window_action` returns `False` (not raise) when KWin or `journalctl` is unavailable
- [x] `MainWindow._on_start_requested` delegates to `_launch_paths`; `_on_stop_requested` and `_on_activate_requested` delegate to `perform_window_action`
- [x] Live smoke: Activate bounces the real ag-scripts VSCode window to the front
- [x] No auto-refresh after Stop (documented rationale: VSCode's save-changes dialog may stall the close; user-triggered Refresh is correct)
- [x] Tests pass (82 total, 11 new)

## Architecture

### Modified

- `window_scanner.py`:
  - Constants `ACTION_CLOSE`, `ACTION_ACTIVATE`, `ACTION_LOG_PREFIX`, `ACTION_SCRIPT_NAME`
  - `_build_action_script(label, action)` — pure function, generates the KWin JS source with JSON-encoded label and action-dispatch already inlined
  - `action_succeeded(journal_text)` — pure check for the `VSCL_ACTION_OK:` marker
  - `WindowScanner.perform_window_action(label, action)` — load / run / unload + journal check, mirrors `list_vscode_captions` structure

- `vscode_launcher.py`:
  - `WorkspaceListWidget` gains `start_requested`, `stop_requested`, `activate_requested` signals
  - Row widget adds contextual `QPushButton`s with `NoFocus` policy
  - `MainWindow._build_ui` connects the three signals
  - New handlers: `_on_start_requested`, `_on_stop_requested`, `_on_activate_requested`
  - New helper: `_find_workspace_by_path`

### Why not a separate `WindowController` class

`WindowScanner` already owns the KWin/qdbus/journalctl invocation pattern. Splitting would duplicate ~40 lines of subprocess-plumbing boilerplate for no clarity gain. The scanner's responsibility evolved from "enumerate" to "enumerate and act on" — a small scope widening, not a new concept.

## Implementation Notes

- The action script is generated fresh per call and uploaded with a unique temp-file name, but loaded into KWin under a fixed `vscode-launcher-action` script id so the `finally` block can unload it deterministically
- `closeWindow()` is asynchronous; the `VSCL_ACTION_OK:` log line is emitted synchronously before `closeWindow()` returns (i.e., before the unsaved-changes dialog, if any). So `True` means "the close request was accepted", not "the window is now gone"
- `workspace.activeWindow = w` is a property assignment in the KWin JS API; it handles both stacking-order raise and keyboard-focus transfer
- Labels are passed through `json.dumps` for safe JS string-literal insertion. A property-based test-like case in the unit suite proves embedded quotes don't escape.

## Open Questions (deferred)

- **Auto-refresh after Stop**: deferred until a signal exists that distinguishes "window actually closed" from "close dialog is pending". Could use a KWin `windowRemoved` signal via a persistent registered script; out of scope for now.
- **Stop confirmation in launcher UI**: deferred. VSCode's own save-changes dialog is the authoritative confirmation, and a second dialog on top would be redundant. If users accidentally hit Stop and regret it, they can cancel VSCode's dialog.
