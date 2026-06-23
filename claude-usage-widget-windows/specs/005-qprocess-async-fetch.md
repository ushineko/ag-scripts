# Spec 005: Replace QThread usage fetch with QProcess (crash fix)

> **Note**: This work has no associated issue tracker ticket (personal public repo, per project policy).

## Status: COMPLETE

## Problem

The macOS widget crashed with `Abort trap: 6` (SIGABRT) after a few update
cycles. The crash report's faulting (main) thread shows:

```
abort  ←  QMessageLogger::fatal()  ←  QThread::~QThread()  ←  QThreadWrapper::~QThreadWrapper()  ←  deleteLater (QObject::event)
```

This is Qt's "QThread: Destroyed while thread is still running" guard calling
`qFatal()`. In `run_gui()`, `on_data_ready` was connected to the worker's
`result_ready` signal, which is emitted as the **last line of `QThread.run()`** —
before the thread has actually terminated. Calling `worker.deleteLater()` from
that handler races thread shutdown; if the deferred delete is processed before
the thread finishes, `~QThread` aborts the process. The race is timing
dependent, hence "crashes after a short time."

## Decision

Follow the repo's established async convention: a main-thread `QProcess` driven
by the Qt event loop (as in `vscode-launcher/window_scanner.py` v1.7 and
`vpn-toggle/vpn_toggle/monitor.py`), instead of `QThread`. The sibling
`peripheral-battery-monitor` hit the identical QThread crash (its spec 010);
this project moves off threads entirely rather than patching thread lifecycle.

## Implementation

- `src/fetcher.py` — `UsageFetcher(QObject)`: `start()` spawns a short-lived
  child process via `QProcess`, parses its stdout JSON on `finished`, and emits
  `result_ready(data)` exactly once (guarded against the `finished` /
  `errorOccurred` double-fire). The child is the app's own binary:
  `[sys.executable, "--fetch-json"]` when frozen, `[sys.executable, "-m",
  "src.main", "--fetch-json"]` from source.
- `src/main.py` — added `--fetch-json` (fetch usage, print JSON to stdout, exit).
  In that mode logs are routed to **stderr** so stdout carries only JSON. The
  GUI path uses `UsageFetcher` instead of the `QThread` worker; the fetcher is
  released with `deleteLater()` from `on_data_ready` (safe: a QObject, and the
  child process has already finished).
- `src/logging_config.py` — `setup_logging(..., stream=...)` to send the
  fetch child's logs to stderr.

## Acceptance Criteria

- [x] No SIGABRT/`QThread::~QThread()` crash across many update cycles (verified: bundled `.app` ran 33 fetch cycles at a 3s interval, ~90s, no crash and no new crash report)
- [x] Usage fetch runs via `QProcess` on the Qt event loop; no `QThread` remains in the project (`grep QThread src/` → none)
- [x] `--fetch-json` prints valid JSON to stdout with logs on stderr (verified from source and from the frozen binary)
- [x] Overlapping fetches are prevented (busy guard: `fetcher is not None`)
- [x] Widget/tray still update from fetched data; manual refresh + periodic timer unchanged
- [x] Tests cover command construction (frozen vs source) and JSON parsing; existing tests pass (70 passing)
- [x] Validation report created in `validation-reports/`
