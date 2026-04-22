# Spec 011: IPC-Based Scanner (v2.0)

**Status: COMPLETE**

## Description

Replaces the KWin-scripting + journalctl scanner with a direct client to
VSCode's internal Node-IPC protocol. Research findings are in
[research/README.md](../research/README.md); the protocol-speaking Python
module is [vscode_ipc.py](../vscode_ipc.py).

The window scanner switches from "load a KWin script, run it, wait for its
`console.log` to flush to journald, read and parse the log output" (~500 ms
per scan, KDE-only, subject to a journalctl flush race that required the
v1.8.1 nonce workaround) to "connect to the VSCode main socket, send one
RPC call, deserialize the response" (~3 ms per scan, platform-independent
in principle, atomic response with no race possible).

## Goals

- Drop the ~170× latency overhead of the KWin round-trip path
- Delete every v1.6/v1.7/v1.8.1 workaround that existed only because KWin
  scanning was slow and racy (QProcess state machine, per-scan nonces,
  journal-window tuning, async-scan-finished signal plumbing)
- Keep the existing MainWindow contract so only the scanner backend
  changes; UI behavior is identical to v1.8.1 from the user's perspective
- Free upgrade: per-window `launched_at` becomes accurate for every running
  window, not just launcher-spawned ones, because IPC reports the real
  renderer PID (Electron's Wayland surfaces all report the main PID to
  KWin, so v1.8 couldn't do this)

## Non-Goals

- **Cross-platform window ACTIONS.** Close / Activate still use KWin
  scripting via qdbus6 — a separate investigation per spec 010's open
  questions. This spec scopes to the *read* path only.
- **Moving launches to the IPC `launch.start` RPC.** Current `Popen(['code',
  '--new-window', path])` works; switching it could shave ~100 ms of
  Electron CLI startup but is not necessary for the scanner fix.

## Requirements

### `vscode_ipc.py`

- Locates the VSCode main socket under `$XDG_RUNTIME_DIR` (fallback
  `/run/user/<uid>`) via `vscode-*-main.sock` glob; picks the
  most-recently-modified when multiple exist (survives VSCode restarts
  without cleanup).
- Speaks the full VSCode Node-IPC protocol:
  - 13-byte framing header (`ProtocolMessageType`, id, ack, body length)
  - VSBuffer tagged-TLV serialization (7 data types, VQL-encoded lengths)
  - One-shot client handshake: send ctx string as a single Regular frame
  - RPC: serialize `[RequestType.Promise, id, channel, method]` + `arg`
    as the body of a Regular frame
  - Parse response: `[ResponseType.PromiseSuccess, id]` + return value
- Exposes two high-level functions:
  - `get_main_diagnostics()` — returns the full VSCode diagnostics payload
  - `list_vscode_windows()` — shorthand returning just the `windows` list
- Distinguishes "VSCode not running" (socket missing → `[]`) from
  "transient IPC failure" (socket present but call failed → `None`).
- Swallows all socket and protocol errors to `None`; never raises from
  public entry points. Callers retry on next tick.

### `window_scanner.py` refactor

- `WindowScanner.list_vscode_entries()` delegates to
  `vscode_ipc.list_vscode_windows()` and translates the response to the
  existing `{c: caption, p: pid}` format that MainWindow already consumes.
  Caller code in MainWindow is unchanged.
- `WindowScanner.list_vscode_captions()` stays as a wrapper.
- `WindowScanner.perform_window_action(label, action)` remains on KWin
  scripting for Close / Activate.
- Deleted (no longer needed):
  - `KWIN_ENUMERATE_SCRIPT`, `build_enumerate_script`
  - `parse_scan_entries_from_journal`, `parse_captions_from_journal`
  - Per-scan nonce generator and nonce-aware parser
  - Every QProcess state-machine method on the scanner
  - `WindowScanner.start_async_scan`, `scan_finished` signal
  - `_ScanWorker` / `QThread` plumbing in MainWindow

### `MainWindow` simplification

- Constructor no longer connects to a `scan_finished` signal; the scanner
  is no longer a QObject.
- `_trigger_background_scan` is now ~15 lines: visibility check, one
  sync call to `list_vscode_entries()`, flip detection, re-sort on flip
  or launched-column refresh on no-flip.
- `_on_background_scan_done` is gone. Its logic moved inline into
  `_trigger_background_scan` since there's no longer an async boundary.
- No more `_scan_thread` / `_scan_worker` attributes. No more
  `_on_scan_thread_done` cleanup.
- Closing the window no longer needs to wait on any in-flight thread.

### Install script

- Still installs the desktop entry, symlinks, zsh hook, etc.
- No longer checks for `journalctl`. Scanning doesn't use it.
- Still checks for `qdbus6` but downgrades the missing-qdbus6 message to
  "Stop / Activate will be no-ops" (reading works without it now).

## Acceptance Criteria

- [x] `vscode_ipc.list_vscode_windows()` returns per-window dicts
  `{id, pid, title, folderURIs, remoteAuthority}` on a live VSCode instance
  in ~3 ms
- [x] Returns `[]` when VSCode is not running (distinguished from `None`
  for transient IPC failures)
- [x] Returns `None` on any socket connection / protocol failure
- [x] Never raises from public entry points
- [x] Scan path no longer invokes `qdbus6` or `journalctl`
- [x] Per-window `launched_at` is now accurate for every running window
  (verified live: distinct `/proc/<renderer_pid>/stat` values for
  different windows)
- [x] `WindowScanner.list_vscode_entries()` translates IPC response to the
  existing `{c, p}` format; MainWindow is unchanged
- [x] `WindowScanner.perform_window_action()` still works via KWin
  scripting
- [x] `MainWindow._trigger_background_scan` calls sync, inline.
  No QThread, no QProcess, no scan_finished signal.
- [x] Tests pass: 130 total (32 new for vscode_ipc, ~100 existing,
  ~4 migrated from the v1.x async-signal pattern)
- [x] Live end-to-end works on author's KDE Plasma 6 setup

## Architecture

### New module

`vscode_ipc.py`:

- Pure protocol code, no Qt dependencies
- Could be reused outside this launcher (it's a general-purpose VSCode
  IPC client)
- ~280 lines including docstring, types, and helpers

### `window_scanner.py` after refactor

- Was 500+ lines (KWin scripting + journalctl + nonce machinery + QProcess
  state machine + actions)
- Now ~240 lines (helpers + IPC delegation + KWin actions)
- KWin-specific code is confined to `perform_window_action` and its
  helpers

### `vscode_launcher.py` after refactor

- `MainWindow.__init__` shrinks by ~20 lines (no `_scan_thread` / `_scan_worker`
  init, no signal wiring)
- `_trigger_background_scan` + deleted `_on_background_scan_done` collapse
  into a single method of ~25 lines
- `closeEvent` no longer needs the `try/except RuntimeError` / thread-wait
  dance
- Module version bumped to `2.0`

## Implementation Notes

- Protocol constants (`DataType` tags, `ProtocolMessageType` values, `RequestType` /
  `ResponseType` numbers) are declared as Python module-level constants in
  `vscode_ipc.py` with the same names as VSCode's TypeScript enum members
  for ease of cross-reference.
- The VQL codec accepts and produces big non-negative integers; VSCode uses
  it for buffer lengths and array counts.
- `_serialize(bool)` is handled specifically to produce a JSON Object
  because VSCode's `serialize()` doesn't have a dedicated boolean branch
  (the real VSCode path falls through to `JSON.stringify`). Roundtrip works
  either way but matching the server's behavior keeps things predictable.
- Socket discovery uses `os.stat(...).st_mtime` for ordering. When VSCode
  has been restarted without cleanup, the most-recent socket is the live
  one.

### Why not switch Close / Activate too

`launch.start({args: ["--reuse-window", path]})` via IPC is plausibly the
Activate replacement. Close has no obvious counterpart in the public
channel surface so far explored. Dropping KWin for actions is a future
step that requires investigating the `window` channel and related RPCs.
Out of scope for v2.0, which aims to fix the scanner reliability (nonce
workaround) and latency issues while keeping the known-good action path.

## Platform abstraction + cleanup (within v2.0)

A companion pass after the main refactor landed:

- **New module `platform_support.py`** centralizes every place the Linux-only
  assumptions would change when porting to macOS or Windows:
  - `vscode_state_db_path()` — Linux/mac/Windows branches with stubs for
    unsupported platforms (returns `None` instead of raising).
  - `vscode_ipc_socket_candidates()` — Linux implementation via
    `$XDG_RUNTIME_DIR` glob; macOS/Windows are `TODO(...)` stubs with
    porting notes inline.
  - `process_start_time(pid)` — moved from `window_scanner.py`. Linux
    reads `/proc`; macOS/Windows return None (caller degrades the
    Launched column to em-dash for pre-existing windows until implemented).
  - `launcher_config_dir()` — `~/.config/vscode-launcher` on Linux/mac,
    `%APPDATA%\vscode-launcher` on Windows.
- **No more `sys.platform` branches scattered across the codebase.** A grep
  confirms `platform_support.py` is the only file with OS checks.
- **Dead code removed**: `_refresh_launched_at` in `MainWindow`. It existed
  to retry `launched_at` when KWin temporarily reported `pid=None` (pre-v2.0
  race). With IPC, pids are always reliable, so the retry path never fires.
  Deleted along with the second copy of the `pid_by_label` loop it carried.
- **Duplication factored**: the `pid_by_label` loop is now a `@staticmethod`
  helper (`MainWindow._pid_by_label`) reused by `_apply_running_and_sort`
  (the only remaining caller).
- **KWin action plumbing is intentionally NOT abstracted** by `platform_support`.
  It's KDE-specific and already feature-gates on `qdbus6` availability
  internally. A cross-platform port would replace it wholesale with
  something else (IPC `launch.start` for activate; `kill` or a `window`
  RPC for close). Abstracting prematurely would add an indirection with
  no benefit.

## Memory

Two memories already saved during v1.6–v1.8 debugging remain relevant:

- `feedback_pyqt_qthread_worker_pattern` — still useful when a thread is
  the right tool (CPU-bound Python work that isn't subprocess-driven)
- `feedback_pyqt_qprocess_over_qthread` — sibling pattern; still the right
  advice for subprocess-heavy work

A new lesson worth capturing from this refactor: **"check for a native
protocol before building an OS-level scraping solution"**. The v1.x
implementation was a well-engineered scraper, but the direct approach
(talk to the service, not the compositor it renders into) was available
the whole time. Research took one session; the rewrite was ~300 lines.
