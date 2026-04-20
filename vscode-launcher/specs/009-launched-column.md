# Spec 009: Launched Column

**Status: COMPLETE**

## Description

Adds a **Launched** column to the workspace grid showing how long ago each running VSCode window was opened (relative time, e.g., `5m ago`, `2h ago`, `3d ago`). Non-running rows show an em-dash.

The launched time is populated from two sources with precedence:

1. **In-memory tracking** of launches the launcher itself spawned — exact per-window timestamp
2. **`/proc` fallback** using the window's PID from KWin — gives "VSCode-started-at" (same for every window, because KWin reports the main-VSCode PID for all Electron windows); useful only as a lower bound for windows that were open before the launcher started

## Problem

Empty answer: "when did I open this workspace?" — previously there was no signal in the UI. The user had to remember.

Naive answer: "just look at `w.pid` in KWin and read /proc" — doesn't work. KWin reports the **main VSCode process PID** for every window (Electron's single-process-owns-all-windows model). All six open windows would show "9h ago" if that's when VSCode itself started.

Real answer: track launches we perform, fall back to VSCode-main-started for external opens.

## Goals

- Per-row, accurate launch time for workspaces the user opens via the launcher's Start button or context-menu Launch
- Honest lower-bound for workspaces VSCode had open before the launcher started (shows VSCode-started-at — "the window has been open *at most* this long")
- Live-updating relative time in the UI (the `5m ago` ticks up to `6m ago` without a manual Refresh)
- Zero new dependencies (read `/proc/<pid>/stat` + `/proc/stat btime`, both kernel-provided)

## Non-Goals

- Per-window launch time for windows opened outside the launcher. Electron's process model makes this fundamentally hard, and the use case (VSCode-main-started-at as lower bound) is sufficient.
- Persisting launch times across launcher restarts. The in-memory dict resets every time the launcher starts. Worth revisiting if the user reports it.

## Requirements

### Scan payload enriched with pid

- `KWIN_ENUMERATE_SCRIPT` now emits `[{c: caption, p: pid}, ...]` instead of `[caption, ...]`
- `parse_scan_entries_from_journal` is the new primary parser; `parse_captions_from_journal` becomes a backward-compat wrapper returning only the captions
- `WindowScanner.list_vscode_entries()` is the new sync API; `list_vscode_captions()` is kept as a wrapper
- `WindowScanner.scan_finished` signal carries the new entries shape
- Legacy format (list of bare strings) is tolerated by both parsers — treated as `{c: caption, p: None}`

### Process start time helper

- `get_process_start_time(pid) -> float | None` in `window_scanner.py`
- Reads `/proc/<pid>/stat` field 22 (starttime in clock ticks since boot) — the line is parsed safely by taking `rindex(b")")` to handle comms with spaces/parens
- Combines with `/proc/stat` `btime` (seconds since epoch at boot) and `sysconf("SC_CLK_TCK")` (Hz)
- Returns None for any failure (bad pid, race, permission, `/proc` not present)

### In-memory launch tracking

- `MainWindow._launched_at_by_path: dict[str, float]`
- Populated in `_launch_paths`: after each successful `launcher.launch_workspace(ws)`, record `time.time()` keyed by `ws.path`
- Cleared when a workspace transitions running → not-running (prevents stale timestamps if the user relaunches the same workspace later)

### Precedence in `_apply_running_and_sort`

- For each running workspace:
  1. If `self._launched_at_by_path.get(ws.path)` is set → use it
  2. Else if the scanner gave us a pid → `get_process_start_time(pid)`
  3. Else → None
- For each non-running workspace: `launched_at = None` and `_launched_at_by_path.pop(ws.path, None)`

### New column

- `COL_LAUNCHED = 3` between Status (col 2) and Tmux (col 4); Actions shifts to col 5
- Width: 100 px fixed
- Cell: `QLabel` with `color: gray` containing `format_relative_time(ws.launched_at)`
- `WorkspaceTableWidget.refresh_launched_cells(workspaces_by_path)` updates only the Launched column across all rows — called on every auto-refresh tick (even when no flips) so relative times stay current without a full reload

### `format_relative_time` helper

- `None` → `"—"`
- `< 60 s` → `"just now"`
- `< 3600 s` → `"{N}m ago"` (integer minutes)
- `< 86400 s` → `"{N}h ago"`
- else → `"{N}d ago"`
- Accepts an optional `now` parameter for deterministic testing

## Acceptance Criteria

- [x] `KWIN_ENUMERATE_SCRIPT` emits `[{c, p}, ...]`; Python parses it into `list[dict]`
- [x] Legacy `[caption, ...]` payload still parses (wrapped with `p: None`)
- [x] `get_process_start_time(pid)` returns a Unix timestamp or None
- [x] `WindowScanner.list_vscode_entries()` — new sync API
- [x] `WindowScanner.list_vscode_captions()` — backward-compat wrapper
- [x] `MainWindow._launched_at_by_path` records a timestamp per successful launch
- [x] `_apply_running_and_sort` precedence: tracked > /proc > None
- [x] Tracking entry cleared when workspace transitions running → not-running
- [x] New `COL_LAUNCHED` column between Status and Tmux
- [x] Launched cell shows relative time for running rows, em-dash for non-running
- [x] `refresh_launched_cells` updates only the Launched column on every tick without flips
- [x] `format_relative_time` unit-tested across all time-range branches
- [x] Full test suite passes (99 tests)

## Architecture

### Data flow

```
┌─────────────────────────────────────────────────────────────────┐
│ User clicks Start on workspace X                                │
│   │                                                             │
│   ▼                                                             │
│ _launch_paths: Popen("code --new-window X")                     │
│   │  self._launched_at_by_path[X.path] = time.time()            │
│   ▼                                                             │
│ ~5s later: auto-refresh scan detects X now running              │
│   │                                                             │
│   ▼                                                             │
│ _on_background_scan_done → flip detected                        │
│   │                                                             │
│   ▼                                                             │
│ _apply_running_and_sort:                                        │
│   X.launched_at = tracked (exact)                               │
│   Other running workspaces: launched_at = /proc fallback        │
│   (same VSCode-main-started time for all)                       │
│   Sort running-first                                            │
│   │                                                             │
│   ▼                                                             │
│ _reload_list → Launched column rebuilt from workspace.launched_at│
└─────────────────────────────────────────────────────────────────┘

Subsequent no-flip ticks:
   refresh_launched_cells → relative times tick forward in-place
```

### Why not persist across restarts

Keeping tracking in memory only means the user sees "—" for windows opened before the launcher last started, even if they were launched via the launcher in a previous session. The alternative — persisting to `workspaces.json` — adds stale-entry bookkeeping for little gain in the common case (users don't restart the launcher frequently).

## Implementation Notes

- `_apply_running_and_sort` became an instance method (was `@staticmethod` in v1.7) so it can read `self._launched_at_by_path`. Consumers already called it via `self.`.
- The `refresh_launched_cells` approach (in-place cell updates) reuses ideas from v1.6 but scoped to a single column — the lesson from spec 007 was that rebuilding the whole table every tick is disruptive.
- Matching `pid → workspace label` uses the same ` - ` token-split logic as the running-detection path (spec 004); `aiq-ralph` doesn't claim an `aiq-ralphbox` window's pid.

## Alternatives Considered

- **`psutil`** — would simplify `get_process_start_time` to one call. Rejected: adds an external dependency for one small function, and the CLAUDE.md policy says to ask before installing.
- **Per-window pid via Electron's IPC** — would need an injected extension or the VSCode remote-debug protocol. Way out of scope.
- **`pgrep` / `ps --sort=start` tracking of zygote start times** — fragile correlation, brittle to VSCode internals changing, not worth the complexity.
- **Show absolute time** (`14:32`) instead of relative — less informative for "how long has this been open?"; rejected.
