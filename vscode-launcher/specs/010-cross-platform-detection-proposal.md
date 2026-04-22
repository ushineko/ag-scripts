# Spec 010: Cross-Platform Window Detection (Proposal)

**Status: PROPOSAL** — design only, not implemented

## Problem

The v1.x running-state detection is tightly coupled to KDE Plasma 6 because
it relies on KWin's JavaScript scripting API (`loadScript` / `Script.run` via
`qdbus6`) plus `journalctl --user -u plasma-kwin_wayland` as the out-of-band
result channel. This works on the author's setup but forecloses the tool
from GNOME, non-KDE desktops, macOS, or Windows.

Goal: a design that keeps the v1.x behavior on KDE (where it's fast and
stable) while adding a portable fallback that works anywhere VSCode itself
runs.

## Findings from probing

### `code --status`

The documented CLI command `code --status` returns per-window information
including PID and window title. Example line on Linux:

```
    0  346198835977  2372593  window [1] (EMM endpoints for CVE-re… - platform-backend (Workspace) - Visual Studio Code)
    0  346198835977  2492977  window [2] (Spec vscode-launcher too… - ag-scripts - Visual Studio Code)
```

For each running VSCode window the CLI provides:

- Renderer process PID (a *real* per-window PID, not the main-VSCode PID
  that KWin reports). Accurate `launched_at` via `/proc/<pid>/stat` becomes
  possible for ALL running windows, including ones VSCode had open before
  the launcher started.
- Full caption string in the same `<file> - <label> - Visual Studio Code`
  format the launcher already parses.

This is the **richest, most portable** signal obtainable without speaking
VSCode's internal protocol.

**Cost**: ~2.4 s wall-clock per invocation on the author's i9-14900K. The
Electron CLI has to spin up, open the IPC socket, round-trip, and print.
Far too slow for a 5-second polling loop (~50 % of time would be spent in
`code --status`). Acceptable for startup / manual Refresh only.

### VSCode IPC socket (`/run/user/<uid>/vscode-<session>-main.sock`)

Probed directly. Does **not** accept plain HTTP or bare JSON. Uses VSCode's
internal `vs/base/parts/ipc/node/ipc.net` framing: length-prefixed binary
with handshake opcodes, message IDs, and VSCode's custom buffer format.
Connecting from Python times out without the expected handshake.

Writing a Python client for this protocol is feasible (VSCode is MIT-
licensed, so the wire format can be mirrored) but estimated at **a few
hundred lines of protocol code** that must track VSCode's internal version
updates.

### VSCode extension

A small extension could publish open-workspace state to a known file or
socket, providing instant, stable per-window data. But: every user would
have to install the extension, and the installation/update flow is a
separate concern from the launcher itself. Deferred as out of scope.

## Proposed architecture

A new `WorkspaceInspector` abstraction with pluggable backends. The table
widget / MainWindow stays backend-agnostic.

```text
WorkspaceInspector (abstract)
   │  list_entries() -> list[WindowEntry] | None
   │  start_async_scan() -> scan_finished(list[WindowEntry] | None)
   │
   ├── KWinInspector      (current impl, fast poll on KDE)
   ├── CodeStatusInspector (code --status text parse, portable but slow)
   └── CompositeInspector  (fastpath + fallback strategy)
```

`WindowEntry` is the existing `{c: caption, p: pid}` dict, unchanged.

### Platform selection

Auto-detect at startup:

1. If `qdbus6` + `journalctl` + `plasma-kwin_wayland` unit present → use
   `KWinInspector` primary with `CodeStatusInspector` as slow-path fallback
   on manual Refresh.
2. Otherwise → `CodeStatusInspector` primary, no polling fallback.

The fallback path is deliberately asymmetric: KWin is fast enough to both
poll AND answer manual Refresh; `code --status` is only fast enough for
event-driven calls (manual Refresh, initial load, after-launch grace).

### Polling trade-off on non-KDE

With `CodeStatusInspector` as the only backend, auto-refresh becomes
impractical (2.4 s per scan × 5 s interval = 48 % duty cycle). Options:

- **A. Disable auto-refresh on non-KDE.** Users hit Refresh manually. Honest,
  simple, no surprising battery hit.
- **B. Poll at a 30–60 s interval on non-KDE.** Less disruptive, still gives
  periodic freshness.
- **C. Use filesystem watching on `~/.config/Code/User/workspaceStorage/`**
  as a cheap "did anything happen?" trigger, then invoke `code --status`
  only when mtime changed. Heuristic, but elegant.

Recommend (A) for the first port, (B) as a setting later.

### Per-window launch time everywhere

`code --status` surfaces renderer PIDs. `/proc/<pid>/stat` works the same
on any Linux. On macOS/Windows the per-process start-time helper would
swap in `os.stat` or platform-specific calls. The Launched column becomes
correct per-window on every platform, an upgrade over the current
"main-VSCode-started-at" lower bound.

## Open questions

- **Action flow** (Activate / Stop / Start) also uses KWin scripting.
  Cross-platform equivalents needed:
  - **Start** is already portable (`Popen(["code", "--new-window", path])`).
  - **Stop**: `code --command workbench.action.closeWindow` with an
    active-window selector? Needs investigation. Or `kill <renderer_pid>`
    (hard), `killall code --signal SIGINT` (nuclear).
  - **Activate**: `code --reuse-window <path>` focuses an existing window.
    Plausibly the cross-platform equivalent of "activate". Needs
    confirmation.

- **State DB path** on non-Linux:
  - macOS: `~/Library/Application Support/Code/User/globalStorage/state.vscdb`
  - Windows: `%APPDATA%\Code\User\globalStorage\state.vscdb`
  - Current code hardcodes the Linux path.

- **Tmux integration** is Linux+tmux specific. On macOS it could work the
  same; on Windows it's N/A. The config schema already handles "no tmux
  session" gracefully (empty string), so this is more a feature-gate
  question than an architecture one.

## Scope estimate

Roughly ordered by effort:

| Work item | Complexity | Notes |
| --------- | ---------- | ----- |
| Refactor into `WorkspaceInspector` interface | S | Mechanical |
| Implement `CodeStatusInspector` (text parse) | S–M | Output format is stable and simple |
| Composite backend + auto-detect logic | S | 20–30 lines |
| Platform-specific `VSCODE_DB_PATH` | S | One-line detection |
| Tests (new backend + auto-detect) | M | |
| Cross-platform action flow (close / activate) | M | Requires investigation per platform |
| VSCode IPC protocol Python client | L | Ambitious; 200+ lines, version-fragile |
| VSCode extension for per-window state | L | Separate codebase, distribution story |

Estimate for a "runs on non-KDE Linux with `code --status`" milestone:
~2–3 focused sessions of work. Not counting macOS/Windows action flow.

## Recommendation

**Don't rewrite yet.** The current KWin-based v1.x is working for the
author's primary use case (KDE Plasma on CachyOS). A cross-platform port is
a real multi-day project with genuine research components (especially
cross-platform window actions).

**When we do port**, the path forward is:

1. Refactor scanner into `WorkspaceInspector` with two backends
2. Ship `CodeStatusInspector` + manual-Refresh-only mode on non-KDE
3. Defer IPC protocol and VSCode extension approaches unless polling cost
   becomes the bottleneck

**Nice immediate win from this research** (independent of a full port):
`code --status` gives us accurate per-window launch times. Even on KDE, we
could run it **once** on startup and once after a manual Refresh to correct
the Launched column's "VSCode-started-at" fallback for pre-existing
windows. ~2.4 s cost amortized across startup is fine. Everything else
(5-s polling) keeps using KWin as today.

## Memory note

The research outcome is worth a cross-project memory entry: when an
Electron/Chromium app uses the Wayland-single-surface-per-process model,
external tools cannot correlate per-window state via the compositor alone.
`code --status` is the canonical pattern — the app's own CLI is the
escape hatch, at Electron-startup cost.
