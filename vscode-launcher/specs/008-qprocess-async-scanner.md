# Spec 008: QProcess-Based Async Scanner

**Status: COMPLETE**

## Description

Replaces the `QThread` + `_ScanWorker` auto-refresh machinery from spec 007 with a `QProcess` state-machine inside `WindowScanner`. No threads are spawned; each subprocess invocation is driven by Qt's event loop.

This removes the two PyQt GC invariants that bit the v1.6 implementation (silent no-run when the worker was prematurely collected; `wrapped C/C++ object deleted` crash on the next tick). Threading was the wrong abstraction from the start. The threads only existed to hide `subprocess.run`'s blocking nature, and `QProcess` is inherently async via Qt's event loop.

## Goals

- Same user-visible behavior as v1.6 (auto-refresh every 5 s, in-place row updates, no UI freeze)
- Stricter failure mode: no threads means no "worker orphaned by GC" class of bugs
- Reduce MainWindow complexity: the scanner self-manages in-flight state, so the `_trigger_background_scan` path shrinks from ~30 lines to ~5

## Non-Goals

- Rewriting `perform_window_action` (close / activate) to be async — those run on discrete button clicks where a ~500 ms freeze is imperceptible. Scope-limit the refactor to the hot path.
- Removing the synchronous `list_vscode_captions()` — still used by the manual Refresh on startup and by existing tests. The two implementations coexist; the sync one is selected for rare blocking callers, the async one for the polling loop.
- Adding `qasync` / `asyncio` — the state machine for 3 sequential subprocesses is small enough that callbacks are readable.

## Requirements

### `WindowScanner` is now a `QObject`

- Exposes `scan_finished = pyqtSignal(object)` carrying `list[str] | None`
- `start_async_scan()` kicks off the chain:
  1. Write the KWin JS script to a temp file
  2. `qdbus6 … loadScript` (async via `QProcess`)
  3. On `finished(0, …)`: parse the script id from stdout, then `qdbus6 … Script.run`
  4. On `finished`: wait 300 ms via `QTimer.singleShot` for KWin's `console.log` to hit the journal
  5. `journalctl …`
  6. On `finished`: parse captions, emit `scan_finished(captions)`
- Errors at any step emit `scan_finished(None)` (no partial state leaks)
- `errorOccurred` on any `QProcess` also terminates the chain cleanly
- In-flight guard: a second `start_async_scan()` call while a scan is running is a silent no-op — callers don't need their own reentrance lock
- Cleanup in `_finish_async`:
  - Fires a fire-and-forget `qdbus6 … unloadScript`. No wait for the result since the captions are already in hand.
  - `os.unlink()`s the temp script file
  - Calls `deleteLater()` on all tracked `QProcess` instances and the delay timer
  - Resets state fields to `None` and flips `_scan_in_progress` back to `False`

### `MainWindow` simplifications

- `_ScanWorker` class removed
- `_scan_thread` / `_scan_worker` attributes removed
- `_on_scan_thread_done` method removed
- `_trigger_background_scan` shrinks to "skip if hidden; call `start_async_scan()`"
- `scan_finished` signal connected once, in `__init__`, to `_on_background_scan_done`
- `closeEvent` no longer calls `thread.quit()` / `wait()` — there's no thread to join

### Sync API kept for sync callers

- `list_vscode_captions()` is unchanged (still blocks on `subprocess.run`)
- Used by `MainWindow._build_workspace_list()` during manual Refresh — the user-initiated path where a brief freeze is expected
- Used by existing unit tests that don't want to pump a Qt event loop

### Test fake compatibility

- `MainWindow.__init__`'s `scan_finished.connect` is guarded by `hasattr(self.window_scanner, "scan_finished")` so test fakes that implement only `list_vscode_captions()` keep working without subclassing `QObject`

## Acceptance Criteria

- [x] `WindowScanner(QObject)` with `scan_finished = pyqtSignal(object)`
- [x] `start_async_scan()` runs the 5-step chain via `QProcess` and emits `scan_finished(list[str] | None)` when done
- [x] In-flight guard: second call while scan is running is a no-op (no queue, no double-run)
- [x] `_finish_async` fires unload, unlinks temp file, and `deleteLater`s all owned `QProcess` + `QTimer` instances
- [x] Any error in the chain (process failure, bad script id, parse failure) emits `scan_finished(None)` cleanly
- [x] Sync `list_vscode_captions()` unchanged for the manual-Refresh path
- [x] `_ScanWorker` class and all `_scan_thread`/`_scan_worker`/`_on_scan_thread_done` references removed from `vscode_launcher.py`
- [x] `_trigger_background_scan` is now ~5 lines (visibility check + `start_async_scan()`)
- [x] `scan_finished` connected once in `MainWindow.__init__`
- [x] `closeEvent` no longer does thread.quit/wait
- [x] `MainWindow.__init__` is resilient to test fakes that don't have `scan_finished` (guarded `hasattr` check)
- [x] Live smoke: real KWin + real journalctl end-to-end returns the expected captions
- [x] Full test suite passes (88 tests)

## Architecture

### State machine (async path)

```text
start_async_scan
   ├─ available? ─no→ emit None
   ├─ already in-flight? ─yes→ no-op
   ├─ write script file → fail→ emit None
   └─ QProcess(qdbus6 loadScript) ──finished──┐
                                              │
      ┌───────────────────────────────────────┘
      │ exit_code != 0? → emit None
      │ parse script_id → fail? → emit None
      │
      └─ QProcess(qdbus6 Script.run) ──finished──┐
                                                 │
         ┌───────────────────────────────────────┘
         │
         └─ QTimer.singleShot(300 ms) ──timeout──┐
                                                 │
            ┌────────────────────────────────────┘
            │
            └─ QProcess(journalctl) ──finished──┐
                                                │
               ┌────────────────────────────────┘
               │ parse captions
               │
               └─ _finish_async(captions) → emit scan_finished(captions)
                      │
                      ├─ fire-and-forget QProcess(qdbus6 unloadScript)
                      ├─ os.unlink(script file)
                      ├─ deleteLater() on all owned QProcess + timer
                      └─ reset state, _scan_in_progress = False
```

### Why async only (and not sync too)

The sync version remains useful for the initial populate on startup and for unit tests that want deterministic results without pumping `QApplication.exec()`. Rewriting it would force test-infrastructure changes (`QTest.qWait`, signal spies) that aren't worth the complexity.

## Implementation Notes

- Each step creates a new `QProcess(self)` rather than reusing one. Parent-child ownership keeps Qt state alive; `deleteLater` in `_finish_async` cleans them up after emission so a QProcess isn't leaked per 5-second cycle.
- `QProcess.errorOccurred` is connected alongside `finished` to catch "failed to start" type errors (e.g., `qdbus6` suddenly disappears), not just non-zero exit codes.
- The `hasattr(scanner, "scan_finished")` duck-typing check in MainWindow lets fakes use plain objects with a `list_vscode_captions()` method. Subclassing every test fake from QObject would mock a surface deeper than the tests need.
- `_finish_async` is idempotent on the cleanup side — even if some fields are `None`, the per-field guards don't raise.

## Memories Saved (for future projects)

Two memory entries were added during this feature's debugging so the same mistakes aren't repeated elsewhere:

- `feedback_pyqt_qthread_worker_pattern.md` — the two GC invariants for `QThread` + worker when a thread genuinely is the right tool (CPU-bound Python work)
- `feedback_pyqt_qprocess_over_qthread.md` — reach for `QProcess` first when the work is subprocess-heavy; threading was solving the wrong problem
