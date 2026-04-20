# Spec 004: Running Sessions Display

**Status: COMPLETE**

## Description

When the launcher opens, each workspace that is currently open in VSCode is marked with a running badge, and those workspaces are sorted ahead of everything else. If the user tries to launch a workspace that is already open, they are prompted — launch anyway (accepts a duplicate window), skip the running ones, or cancel.

## Problem

After v1.2 shipped, the list simply reflected VSCode's recent history with no indication of which workspaces were already open. It was easy to accidentally double-launch a workspace — producing a duplicate VSCode window for the same project — simply because nothing in the launcher surfaced what was already running.

## Solution

A new `WindowScanner` enumerates VSCode windows via KWin scripting (the same D-Bus path used by the sibling `vscode-gather` tool), extracts their captions, and matches workspace labels against them. The main window consumes this signal to:

- Mark running workspaces with a `● running` badge in each row
- Sort running workspaces ahead of the rest, preserving VSCode's MRU order within each group (running ones in MRU order, then non-running ones in MRU order) — relies on Python's guaranteed-stable sort
- Prompt before launching any workspace that is already running

## Requirements

### Window detection

- Enumerate windows with `resourceClass == "code"` via a KWin JS script loaded through `qdbus6 org.kde.KWin /Scripting`
- The script dumps captions to the compositor log with a unique prefix (`VSCL_CAPTIONS:`)
- The Python side reads the log back through `journalctl --user -u plasma-kwin_wayland` (same approach as `vscode-gather`), parses the most recent payload, and returns the list of captions
- The script is unloaded after each scan
- Any failure (qdbus6 / journalctl missing, KWin not responding, bad JSON) returns `None` so the caller can degrade gracefully — `None` means "can't tell", not "nothing is running"

### Caption matching

- VSCode captions follow the pattern `<file-context> - <label> - Visual Studio Code` (space-dash-space separator, confirmed live on the user's system)
- Matching splits the caption on ` - ` and checks for label equality against a resulting token — NOT a substring match. That avoids false positives like `aiq-ralph` matching windows titled `aiq-ralphbox`
- Labels are compared against what `label_for_path` generates, so folder workspaces match the basename (`ag-scripts`) and `.code-workspace` files match with the `(Workspace)` suffix (`syadmin (Workspace)`)

### UI

- Each row shows a green `● running` badge next to the label when the workspace is open
- Running workspaces sort ahead of non-running ones; within each group, VSCode's original recency order is preserved (Python's stable sort guarantees this)
- Clicking Refresh re-runs the scan
- If the user selects at least one running workspace and hits Launch Selected / Launch All, a three-button dialog appears (Launch Anyway / Skip Running / Cancel). "Skip Running" is the default button
- If the scanner is unavailable (KWin or journalctl missing), rows render without badges and launching proceeds without the prompt — feature degrades silently

### Non-requirements

- No automatic polling — scans happen on startup and on manual Refresh only. The ~300–500 ms per-scan cost would be disruptive if polled
- No window activation / focus — the launcher still only opens new windows; it does not focus an existing one

## Acceptance Criteria

- [x] `WindowScanner.list_vscode_captions()` returns a list of captions on success, `None` on any failure
- [x] `caption_matches_label` returns True for the real caption patterns observed live (`<file> - <label> - Visual Studio Code`)
- [x] `caption_matches_label("... - aiq-ralphbox - ...", "aiq-ralph")` is False — prefix-match rejection is a dedicated test
- [x] `running_labels(captions, labels)` returns the set of labels that appear as a token in at least one caption
- [x] `parse_captions_from_journal` picks the most recent `VSCL_CAPTIONS:[...]` line, handles multi-line input, returns `None` on malformed JSON or missing marker
- [x] `MainWindow` accepts an optional `window_scanner`; when provided, `_build_workspace_list` marks each workspace's `is_running` flag and sorts running-first while preserving MRU order within each group (running then non-running, both MRU-ordered)
- [x] Row widget displays a `● running` badge when `workspace.is_running` is true
- [x] `_launch_paths` detects already-running targets and shows a 3-button dialog (Launch Anyway / Skip Running / Cancel)
- [x] When the scanner returns `None`, the list still renders and launching proceeds without the prompt
- [x] `main()` wires `WindowScanner()` into the `MainWindow` by default

## Architecture

### New module

- `window_scanner.py`
  - `WindowScanner.list_vscode_captions() -> list[str] | None`
  - `caption_matches_label(caption, label) -> bool` — pure function, trivially testable
  - `running_labels(captions, labels) -> set[str]` — batch convenience
  - `parse_captions_from_journal(text) -> list[str] | None` — pure parser, most-recent-wins
  - Constants: `SCRIPT_NAME`, `LOG_PREFIX`, `KWIN_ENUMERATE_SCRIPT`

### Modified

- `Workspace` dataclass gains a runtime-only `is_running: bool = False` field (not persisted)
- `MainWindow.__init__` accepts `window_scanner: WindowScanner | None = None`
- `MainWindow._build_workspace_list` calls the scanner (when present), marks workspaces, sorts
- `WorkspaceListWidget._build_row_widget` renders the running badge
- `MainWindow._launch_paths` shows the 3-button prompt when any target is running

## Implementation Notes

- The KWin script uses `console.log` rather than any return-value mechanism because KWin's `Scripting.run` D-Bus call doesn't return a value — the only cross-process signal available is the journal
- A 300 ms sleep between `Script.run` and `journalctl` is needed because `console.log` is asynchronous on KWin's side
- `subprocess.run(..., check=False)` throughout — any failure propagates as `None`, never as an exception
- `shutil.which(qdbus_cmd)` + `shutil.which("journalctl")` is the availability gate
- Unit tests stub `shutil.which`, `subprocess.run`, and `time.sleep`; no live KWin required

## Alternatives Considered

- **`wmctrl` / `xdotool`** — both are X11-only, don't work under Wayland (documented in the project's CLAUDE.md KDE/Wayland notes)
- **`ps` parsing of `code` processes** — VSCode uses a single-process model per user; renderer subprocesses don't carry workspace paths. No signal to extract
- **Polling** — rejected because the scan is ~300–500 ms and disruptive to the UI; manual refresh is sufficient for the user's workflow
- **Auto-focus existing window instead of prompting** — out of scope; would require tracking which KWin window belongs to which workspace and activating it via another KWin script. The prompt is simpler and leaves the user in control
