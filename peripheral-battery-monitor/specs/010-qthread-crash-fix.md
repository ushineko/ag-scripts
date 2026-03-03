# Spec 010: Fix QThread deleteLater Crash

**Status: COMPLETE**

## Description

Fix a recurring crash caused by a QThread lifecycle race condition in the `UpdateThread` worker pattern. The crash manifests as `Fatal Python error: Aborted` from Qt's `qFatal()` during posted event delivery.

## Problem Statement

The crash log at `~/.local/state/peripheral-battery-monitor/crash.log` records 5 identical `Fatal Python error: Aborted` crashes. All stack traces originate inside `QCoreApplicationPrivate::sendPostedEvents()` → `QObject::event()` → `QMessageLogger::fatal()`, which is Qt detecting a destroyed QObject during deferred deletion.

The root cause is in `update_status()` (line 662):

```python
self.worker.finished.connect(self.on_worker_finished)   # sets self.worker = None
self.worker.finished.connect(self.worker.deleteLater)    # schedules C++ deletion
```

When `finished` fires:
1. `on_worker_finished()` sets `self.worker = None`, dropping the Python reference.
2. Python may garbage-collect the wrapper before `deleteLater()` runs.
3. Qt's event loop later processes the deferred delete on a C++ object whose Python wrapper is gone, triggering `qFatal()` → `abort()`.

Additionally, `update_status()` is defined twice (lines 645-648 and 650-663). The first definition is dead code — Python silently replaces it with the second.

## Requirements

### Must

- [ ] Eliminate the `deleteLater` race condition so the app no longer aborts during worker cleanup
- [ ] Remove the duplicate `update_status` method definition (lines 645-648)
- [ ] Preserve existing behavior: worker overlap prevention, 30-second timer cycle, data emission via `data_ready` signal

### Must Not

- [ ] Change the `UpdateThread.run()` logic (subprocess invocation, data parsing)
- [ ] Change the timer interval or signal/slot wiring beyond worker lifecycle
- [ ] Introduce new dependencies

## Proposed Fix

Replace the current pattern:

```python
self.worker = UpdateThread()
self.worker.data_ready.connect(self.on_data_ready)
self.worker.finished.connect(self.on_worker_finished)
self.worker.finished.connect(self.worker.deleteLater)
self.worker.start()
```

With a safe cleanup pattern that waits for the thread to finish before releasing the reference:

```python
self.worker = UpdateThread()
self.worker.data_ready.connect(self.on_data_ready)
self.worker.finished.connect(self._cleanup_worker)
self.worker.start()
```

Where `_cleanup_worker` replaces both `on_worker_finished` and the `deleteLater` call:

```python
def _cleanup_worker(self):
    worker = self.worker
    self.worker = None
    if worker is not None:
        worker.deleteLater()
```

This ensures the Python reference (`worker` local variable) stays alive until `deleteLater()` is scheduled in the same call frame. Qt then owns the C++ deletion timing, and the Python wrapper won't be GC'd prematurely because `deleteLater` increments the C++ refcount internally.

## Acceptance Criteria

- [ ] No `Fatal Python error: Aborted` crashes from worker cleanup (verify by running the app through several update cycles)
- [ ] Only one `update_status` method definition exists
- [ ] Worker overlap prevention still works (rapid timer fires don't spawn multiple threads)
- [ ] Existing tests pass

## Files Changed

- `peripheral-battery-monitor/peripheral-battery.py` — worker lifecycle in `update_status()`, `on_worker_finished()` → `_cleanup_worker()`
