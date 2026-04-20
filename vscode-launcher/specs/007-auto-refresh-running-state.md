# Spec 007: Background Auto-Refresh of Running State

**Status: COMPLETE** (amended in v1.7 — see [spec 008](008-qprocess-async-scanner.md) for the QThread→QProcess transport refactor, and the "v1.7 amendment" note below for the re-sort-on-flip behavior change. The polling cadence and visibility gate described here are unchanged.)

## v1.7 amendment — re-sort on state change

v1.6 originally updated only the Checkbox / Status / Actions cells of flipped rows (in place, no re-sort) to preserve scroll and selection. Feedback: the list no longer reflected the running-first invariant after a poll detected a change. v1.7 now re-sorts the workspace list running-first (stable — MRU preserved within each group) and rebuilds the table whenever at least one row flipped. When no flips happen (the common case for successive polls with no state change), nothing reshuffles — no disruption. This means `update_row_running_state` in-place cell rebuild is no longer reachable and has been removed.

## Description

The launcher polls the KWin window scanner every 5 seconds and updates the running-state column of each row in place, without user interaction. Scroll position, selection, row order, and the config file are all left untouched.

This eliminates the main cause of "stale UI": the user opens or closes a VSCode window and the launcher still shows the old state until they click Refresh.

## Goals

- Running / not-running column reflects reality within 5 s of any change
- No UI freeze during the KWin scan (the scan takes 300–500 ms — would be visible if run on the GUI thread)
- No scroll or selection loss from auto-refresh
- No overhead while the launcher window is minimized

## Non-Goals

- Auto re-reading VSCode recents (new workspaces appearing in recents still require manual Refresh) — recent-list changes are rare and would force a sort + rebuild, which is disruptive mid-session
- Auto re-sort (running rows don't leap to the top mid-poll) — row position is load-bearing for muscle memory
- Event-driven scans (KWin window-added / window-removed signals) — would require a persistent KWin script with a D-Bus callback; out of scope

## Requirements

### Polling

- A single `QTimer` starts in `MainWindow.__init__` (after `_refresh()`) when a `window_scanner` is present
- Interval: `AUTO_REFRESH_INTERVAL_MS = 5000`
- Each tick calls `_trigger_background_scan()`, which:
  - Skips when `window_scanner is None`
  - Skips when `self.isVisible()` is False (window minimized / hidden → no CPU waste)
  - Skips when a previous scan's `QThread` is still running (reentrance guard — the KWin script is registered under a single shared name, so concurrent scans would race)
  - Otherwise spawns a short-lived `QThread` + `_ScanWorker` that invokes `WindowScanner.list_vscode_captions()` off the UI thread

### Worker

- `_ScanWorker(QObject)` with a single `finished = pyqtSignal(object)` carrying `list[str] | None`
- `run()` wraps the scanner call in `try/except Exception` and emits `None` on failure — a background refresh that raises would kill the thread and leak the worker
- Worker is `moveToThread(thread)`; thread starts `worker.run`; on `finished` both the worker and thread self-delete via `deleteLater`

### In-place update

- `_on_background_scan_done(captions)` runs on the UI thread
- For each workspace, compare `new_state = ws.label in running` to `ws.is_running`
- If the state flipped, update `ws.is_running` and call `list_widget.update_row_running_state(row, ws)` which rebuilds exactly three cells:
  - Checkbox cell (to flip enabled/disabled)
  - Status cell (to show / hide the `● running` label)
  - Actions cell (to swap `[Start]` ↔ `[Activate][Stop]`)
- Workspace cell (label + path) and Tmux cell are untouched
- `self.workspaces` order is never reshuffled — running-first sort is a *starting* arrangement, not a live invariant

### Cleanup

- `closeEvent` stops the timer, then `quit()`+`wait(2000)` on an in-flight scan thread before saving config
- The 2-second bound is far above the scan's typical 500 ms upper bound; if it ever hits, Qt will log but the app still exits cleanly

## Acceptance Criteria

- [x] `_ScanWorker.run` calls `WindowScanner.list_vscode_captions()` and emits the result as a `finished(object)` signal
- [x] `_ScanWorker.run` catches `Exception` and emits `None` so worker-thread failures can't crash the UI
- [x] `_trigger_background_scan` skips when `window_scanner is None`, when `isVisible()` is False, and when the previous scan thread is still running
- [x] `_on_background_scan_done(None)` is a no-op — doesn't clobber existing state
- [x] `_on_background_scan_done(captions)` updates each row's `is_running` in place; row order is preserved
- [x] `WorkspaceTableWidget.update_row_running_state(row, ws)` rebuilds only the Checkbox / Status / Actions cells
- [x] Checkbox in a row that transitioned to running becomes disabled (belt-and-suspenders: the spec 006 bulk-launch guard also filters running)
- [x] Checkbox in a row that transitioned to not-running becomes enabled
- [x] Actions cell swaps between `[Start]` and `[Activate][Stop]` in both directions
- [x] Auto-refresh timer is started only when a scanner is provided
- [x] `closeEvent` stops the timer and waits on the in-flight scan thread with a 2 s bound
- [x] Tests cover: in-place update without sort, None-captions safety, visibility gate
- [x] Full test suite passes (88 tests, 3 new)

## Architecture

### Added

- `AUTO_REFRESH_INTERVAL_MS = 5000` constant
- `_ScanWorker(QObject)` — 10-line worker
- `MainWindow._start_auto_refresh`, `_trigger_background_scan`, `_on_background_scan_done` — thread lifecycle + UI-thread callback
- `WorkspaceTableWidget.update_row_running_state(row, workspace)` — in-place cell rebuild
- `QObject`, `QThread` added to Qt imports

### Modified

- `MainWindow.__init__` — tracks `_scan_thread` and `_auto_refresh_timer` state, starts the timer at the end of init
- `MainWindow.closeEvent` — stops timer, waits on thread before saving config

## Implementation Notes

- Why QThread and not `concurrent.futures`: Qt signals emitted from a background thread are auto-marshaled to the receiver's thread (so `_on_background_scan_done` runs on the UI thread). With `concurrent.futures`, we'd need to manually bounce the result back through a `pyqtSignal` — same complexity, more moving parts.
- Why deleteLater both the worker and the thread: standard Qt pattern. The worker is a `QObject` moved to another thread, so `deleteLater` ensures it's destroyed on the correct thread after the signal fires. The thread itself is deleted on `finished`.
- Why the visibility gate: `isVisible()` returns False for minimized or not-yet-shown windows. That's the cheapest "is the user actively looking at this?" signal Qt provides. More nuanced options (active-window tracking, idle detection) aren't worth the complexity.
- Why 5 seconds: empirical tradeoff. A 500 ms scan at a 5 s interval is ~10% scan duty cycle, which is barely noticeable on a modern system. Shorter intervals (2 s) feel slightly snappier but triple the overhead; longer intervals (10 s) feel sluggish when the user has just closed a VSCode window and the launcher still says it's running.

## Alternatives Considered

- **Auto-refresh the whole list (recents + scan + sort + rebuild)** — rejected. Full rebuild every 5 s would destroy scroll position and selection. The user's feedback about the "selection indicator" in v1.3 showed they're attentive to these visual defects.
- **Event-driven via persistent KWin script** — rejected for v1.6. KWin 6 supports `workspace.windowAdded` / `windowRemoved` signals, but we'd need a long-lived script that calls back into our process over D-Bus. Substantial machinery. Revisit if 5 s polling ever feels insufficient.
- **Polling on the UI thread** — rejected. 300-500 ms freeze every 5 s is jank.
- **Running a cheaper detection (e.g., `pgrep code`)** — doesn't distinguish which workspaces are open. Useless for our signal.
