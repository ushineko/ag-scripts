# Spec 009: Event-Driven Monitor (Replace QThread with QTimer + QProcess)

**Status: COMPLETE**

## Overview

Replace `MonitorThread(QThread)` and its blocking `subprocess.run` / `socket.gethostbyname` / `requests.get` calls with a main-thread, event-driven architecture built on `QTimer`, `QProcess`, `QDnsLookup`, and `QNetworkAccessManager`.

## Motivation

Two separate issues converge on the same fix:

1. **Reliability.** Three confirmed SIGSEGV + core-dumped crashes of `vpn-toggle` in one week (2026-04-18, -20, -23). All three core files land at the same offset in `libpython3.14.so.1.0` (`_PyEval_EvalFrameDefault+3148`, inside the `LOAD_DEREF` handler) — a corrupted closure cell inside `json.dump`'s recursive encoder, triggered from a Qt queued-connection slot invoked on a cross-thread signal from `MonitorThread`. Reported via [coredump analysis in validation-reports/2026-04-23-crash-analysis.md].

2. **Architectural cleanliness.** The current `MonitorThread(QThread)` pattern is the exact PyQt anti-pattern captured in user memory: a QThread whose body is entirely I/O-bound subprocess work (`nmcli`, `openvpn3`, `ping`) and DNS/HTTP calls. QProcess, QDnsLookup, and QNetworkAccessManager are native-async replacements that run on the main event loop — no thread lifecycle, no cross-thread signal plumbing, no GIL choreography.

Track A (spec-less refactor of `metrics.py` to append-only JSONL, completed before this spec) already reduced the per-cycle `json.dump` blast radius by several orders of magnitude. Track B (this spec) eliminates the cross-thread dispatch path the crash traverses. Either alone may not fix the CPython 3.14 interpreter bug, but together they remove the conditions that reproduce it.

## Architecture

```text
QTimer (main thread, default 30s interval)
  └─> MonitorController.tick()
       └─> for each monitored VPN:
            VPNCheckSession(vpn, asserts, done_callback)
              │
              ├─ (1) is_vpn_active_async?      QProcess nmcli/openvpn3
              │        └─ not active → IDLE, done
              ├─ (2) grace period active?      QTimer.singleShot(remaining, next)
              ├─ (3) for each assert (serial): AsyncAssert.start() → completed(result)
              ├─ (4) all_passed?
              │        ├─ yes → emit check_completed, record metrics, done
              │        └─ no  → (5) bounce:    BounceOperation state machine
              │                    disconnect QProcess → wait grace → connect QProcess
              └─ cleanup any in-flight async resources
```

All QProcess / QDnsLookup / QNetworkReply instances are strong-referenced in the controller's `_in_flight` registry for their entire lifetime, then cleared from the registry in their completion slot before `.deleteLater()`. This is the GC invariant codified in user memory "PyQt QThread + QObject worker — GC invariants".

Every async operation has a hard timeout via `QTimer.singleShot(timeout_ms, abort)` so a hung subprocess or DNS query cannot wedge a session indefinitely.

## Design decisions

1. **Keep sync `VPNAssert.check()` alongside new async variants.** `AsyncDNSLookupAssert`, `AsyncGeolocationAssert`, `AsyncPingAssert` are new QObject classes with a `completed = pyqtSignal(AssertResult)` signal. The existing sync classes and their tests stay unchanged. Production monitor uses async only.

2. **Serial asserts within a check cycle.** Match current semantic — start assert 1, wait for `completed`, then start assert 2. Parallel asserts would cut cycle time from ~1s to ~0.1s but asserts are usually cheap anyway, and serial is simpler.

3. **Keep `threading.Lock` in `MetricsCollector`.** Post-Track-B the lock is redundant (only the main thread calls `record`), but removing it is a separate cleanup. Zero semantic change now.

4. **Backends get two methods per op: `xxx_sync` and `xxx_async`.** `is_vpn_active_sync(name) -> bool` (existing, used by tests and GUI status queries) and `is_vpn_active_async(name) -> QObject` (new, emits `finished(bool)` for the monitor). Same split for `connect`, `disconnect`, `list`.

5. **`VPNManager` thin dispatch layer.** Public sync surface (`list_vpns`, `is_vpn_active`, `get_vpn_status`) unchanged. Add `*_async` methods that return signal-emitting QObjects.

6. **`MonitorController(QObject)` replaces `MonitorThread(QThread)` wholesale.** Emits the same signals (`status_changed`, `assert_result`, `log_message`, `vpn_disabled`, `check_completed`). `gui.py` keeps all its `.connect()` calls verbatim. Only the construction site swaps `MonitorThread(...)` for `MonitorController(...)`, `.start()` for `.start_monitoring()`, `.stop()` for `.stop_monitoring()`.

7. **Test strategy.** New `test_async_asserts.py` and `test_monitor_controller.py`. Use `QCoreApplication.processEvents()` to pump the event loop in a bounded wait; no new dependencies. Fake the async primitives at module seams (substitute fake `QProcess` / fake `QDnsLookup` subclasses for each test). Existing `test_monitor.py` is rewritten to target `MonitorController`.

## Constraints

- **No blocking calls on the main thread — in the monitor / async assert / async backend code paths.** Any `subprocess.run`, `requests.get`, `socket.gethostbyname`, `time.sleep`, or `QProcess.waitForFinished()` on those code paths is a bug.
- **Scope boundary: monitor-only refactor.** The 11 existing sync call sites in `widgets.py`, `tray.py`, `gui.py` (user-initiated button clicks and status queries), and internal `backends/*.py` helpers remain on the sync API. Those are short-blocking, one-shot, user-initiated operations that the existing app has handled synchronously without responsiveness complaints. Widening the scope to make them async too is out of scope for this spec.
- **Existing sync methods on `VPNManager` and `backends/*.py` stay untouched.** We only *add* new `*_async` methods alongside them. No deprecation, no warnings, no signature changes.
- **Python reference discipline.** Every `QProcess`/`QDnsLookup`/`QNetworkReply` must be strong-referenced until its completion slot runs, then explicitly dropped before `.deleteLater()`.
- **No behavior regressions on emitted signals.** The `check_completed`, `assert_result`, `log_message`, `vpn_disabled`, and `status_changed` signals must fire with the same payloads and at the same lifecycle points as before. Same DataPoint structure emitted to `MetricsCollector`. Same bounce semantics (disconnect → reconnect on failure, disable VPN after threshold).

## Acceptance criteria

### Core architecture

- [x] `MonitorController(QObject)` class exists in `monitor.py` and owns a `QTimer` plus a per-VPN `VPNCheckSession` state machine
- [x] `MonitorThread(QThread)` class is removed from `monitor.py`
- [x] `gui.py` constructs `MonitorController` instead of `MonitorThread`; all five existing signal connections in `gui.py` still work
- [x] No `threading.Thread`, `QThread`, `threading.Event`, or `time.sleep` remains in `monitor.py`

### Async asserts

- [x] `AsyncDNSLookupAssert(QObject)` using `QDnsLookup` exists; emits `completed(AssertResult)`
- [x] `AsyncGeolocationAssert(QObject)` using `QNetworkAccessManager` exists; emits `completed(AssertResult)`
- [x] `AsyncPingAssert(QObject)` using `QProcess` exists; emits `completed(AssertResult)`
- [x] Factory `create_async_assert(config)` dispatches by `type` field
- [x] Each async assert has a hard timeout (default 30s for DNS, 12s for geolocation, 10s for ping) that aborts the op and emits `completed(failure)` if exceeded
- [x] `AssertResult` payload format matches the sync variants byte-for-byte (same `success`, `message`, `details` shape)

### Async backends

- [x] `NMBackend.is_vpn_active_async(name) -> QObject` emits `finished(bool)`
- [x] `NMBackend.connect_async(name) -> QObject` emits `finished(success: bool, message: str)`
- [x] `NMBackend.disconnect_async(name) -> QObject` emits `finished(success: bool, message: str)`
- [x] `OpenVPN3Backend` has the same three async methods
- [x] Existing sync methods (`is_vpn_active`, `connect`, `disconnect`) remain unchanged and still used by tests

### VPN manager

- [x] `VPNManager.is_vpn_active_async(name) -> QObject` exists (dispatches by backend)
- [x] `VPNManager.bounce_vpn_async(name) -> QObject` emits `finished(success, message)` after disconnect → `grace_period_seconds` wait → connect
- [x] `VPNManager` continues to expose sync `list_vpns`, `get_vpn_status`, `get_connection_timestamp`, `get_vpn_details` unchanged

### GUI responsiveness

- [x] Live check: during a 30s check cycle and during a simulated bounce, `QApplication.processEvents()` can be dispatched without the UI freezing — concretely, the "Last check" label in the GUI updates its real-time connection-time counter every second without skip, even while a bounce is in progress
- [x] No `subprocess.run`, `requests.get`, `socket.gethostbyname`, `time.sleep`, or `QProcess.waitForFinished()` in the monitor / async assert / async backend code paths (grep asserts in test suite)

### Resource lifecycle

- [x] Every `QProcess` / `QDnsLookup` / `QNetworkReply` is strong-referenced in `MonitorController._in_flight` from creation to completion
- [x] Each completion slot clears the registry entry before calling `.deleteLater()`
- [x] Stopping the monitor (`stop_monitoring`) cancels any in-flight operations and clears the registry

### Tests

- [x] `tests/test_async_asserts.py` exists with coverage for DNS / Geolocation / Ping success, failure, and timeout paths (9+ tests)
- [x] `tests/test_monitor_controller.py` exists with coverage for: idle → active → assert pass → record, idle → active → assert fail → bounce, grace-period skip, VPN-disabled-on-threshold, stop_monitoring cleans up (6+ tests)
- [x] Existing `tests/test_monitor.py` either rewritten to target `MonitorController` or removed (keep logic coverage, drop the thread-specific bits)
- [x] All existing tests in other files (`test_asserts.py`, `test_vpn_manager.py`, `test_openvpn3.py`, `test_config.py`, `test_gui.py`, `test_graph.py`, `test_metrics.py`) continue to pass unchanged
- [x] Full suite `pytest tests/` passes cleanly

### Validation

Confirmed against the live service after restart on 2026-04-23. See
[`validation-reports/2026-04-23-vpn-toggle-v4.3.0-event-driven-monitor.md`](../validation-reports/2026-04-23-vpn-toggle-v4.3.0-event-driven-monitor.md).

- [x] After implementation, service restarts cleanly via `systemctl --user restart vpn-toggle.service`
- [x] Service runs for ≥ 5 minutes with DNS check cycles appending to `metrics/*.jsonl` once per cycle
- [x] Service log ≥ one `VPN Toggle v3.X started` line and no `ERROR`/`CRITICAL` entries unrelated to configured asserts
- [x] `systemctl --user show vpn-toggle.service -p Result` returns `Result=success` (no core-dump)

## Non-goals

- **Fixing the underlying CPython 3.14 bug.** If the crash reproduces after this spec lands, that is evidence the bug is interpreter-level and warrants an upstream report plus a temporary downgrade to Python 3.13.
- **Parallelizing asserts within a cycle.** Worth doing later, but this spec preserves serial semantics.
- **Removing the `threading.Lock` in `MetricsCollector`.** Deferred as a separate cleanup.
- **Changing the configured check interval or assert timeout defaults.** Values preserved from current config.

## Implementation notes

### Mapping of current operations

| File / method | Replacement |
|---|---|
| `asserts.py DNSLookupAssert.check` → `socket.gethostbyname` | `QDnsLookup(QDnsLookup.Type.A, hostname)` → `.lookup()` → `finished` → `.hostAddressRecords()[0].value()` |
| `asserts.py GeolocationAssert.check` → `requests.get` | `QNetworkAccessManager.get(QNetworkRequest(url))` with `request.setTransferTimeout(10000)` |
| `asserts.py PingAssert.check` → `subprocess.run(['ping', ...])` | `QProcess` → `start('ping', [...])` → `finished` |
| `monitor.py time.sleep(2)` (assert retry backoff) | `QTimer.singleShot(2000, self._retry)` |
| `monitor.py self.config_changed.wait(timeout=check_interval)` | `QTimer(interval=check_interval*1000)` driving `MonitorController.tick` |
| `vpn_manager.py bounce_vpn` → sequential subprocess calls | `BounceOperation(QObject)` state machine: disconnect async → QTimer grace wait → connect async → emit finished |

### QDnsLookup caveats

- No built-in timeout — wrap with `QTimer.singleShot(timeout_ms, self._abort)` where abort calls `.abort()` on the lookup and emits a failure `AssertResult`.
- Returns a list of records — take the first A record (`QDnsLookup.hostAddressRecords()[0].value().toString()`). Failure if list is empty.
- Emits `finished` regardless of success/failure; check `.error()` for status.

### QNetworkAccessManager caveats

- `QNAM` is intended to be reused — create once per controller, not per request.
- `QNetworkReply.finished` emits once per request. Check `.error()` for status. Read body via `.readAll()`.
- `QNetworkRequest.setTransferTimeout(ms)` for wire-level timeout. Wrap with `QTimer.singleShot` for belt-and-suspenders upper bound.

### QProcess caveats

- `started` signal fires when exec succeeded; `errorOccurred` for exec failures (e.g. binary not found).
- `finished(exitCode, exitStatus)` fires once. Drain stdout/stderr via `readAllStandardOutput()` / `readAllStandardError()` in the finished slot.
- No `waitForFinished()` on the main thread.

### Rollback

Single commit for the whole refactor. Revert is `git revert <sha> && systemctl --user restart vpn-toggle.service`. Reversible in minutes.

## Implementation summary

### What landed

- `vpn_toggle/asserts.py`: added `AsyncDNSLookupAssert`, `AsyncGeolocationAssert`, `AsyncPingAssert` QObject classes and `create_async_assert` factory alongside the unchanged sync classes. Each async class arms a `QTimer` hard-timeout and has a one-shot `_done` guard so exactly one `completed` emit can fire per `start()`.
- `vpn_toggle/backends/nm.py`: added `is_vpn_active_async`, `connect_vpn_async`, `disconnect_vpn_async` methods plus the underlying `_NmCmdOp` / `_NmActiveCheckOp` / `_NmConnectOp` / `_NmDisconnectOp` QObject ops. Sync methods are untouched.
- `vpn_toggle/backends/openvpn3.py`: same shape, with the additional complexity that `_Ov3ConnectOp` is a real state machine (cleanup → start → poll → timeout|success) since openvpn3 connect polls `sessions-list` for "Client connected".
- `vpn_toggle/vpn_manager.py`: added `is_vpn_active_async`, `connect_vpn_async`, `disconnect_vpn_async`, `bounce_vpn_async`. `BounceOperation(QObject)` chains disconnect → `QTimer.singleShot(grace_ms)` → connect → emit.
- `vpn_toggle/monitor.py`: `MonitorThread(QThread)` replaced with `MonitorController(QObject)` plus a `VPNCheckSession` per-cycle state machine. Same five signals (`status_changed`, `assert_result`, `log_message`, `vpn_disabled`, `check_completed`). Back-compat `start()`, `stop()`, `isRunning()`, `wait()` shims preserve the `MonitorThread`-style call sites in `gui.py`.
- `vpn_toggle/gui.py` + `vpn_toggle/widgets.py`: `MonitorThread` import/type-hint swapped to `MonitorController`. Attribute `main_window.monitor_thread` retained as-is to minimize churn (semantics differ but wiring is unchanged).
- Tests: `tests/test_monitor.py` removed (tested private QThread internals that no longer exist); replaced with `tests/test_monitor_controller.py` (18 tests) and `tests/test_async_asserts.py` (13 tests). Existing 162 tests unchanged and all green.

Full suite: **193/193 passing.**

### Deviations from the spec

- **Attribute `main_window.monitor_thread` NOT renamed** to `main_window.monitor`. Cosmetic inconsistency vs functional churn across `gui.py`, `widgets.py`, `tray.py`, and four `test_gui.py` tests. Deferred. The attribute holds a `MonitorController` which duck-types the QThread API via `start()` / `stop()` / `isRunning()` / `wait()`, so callers and test mocks work unchanged.
- **`_raise_browser_async` only tries Vivaldi**, whereas the sync version iterated `(vivaldi, firefox, chromium, google-chrome)`. Narrowed to keep the event-driven implementation simple; browser-raise is a best-effort UX nicety, not a correctness-critical path. Reverting to multi-browser iteration is straightforward if needed (a list of fallbacks with `errorOccurred`-driven next-browser dispatch).
- **`BounceOperation` has no dedicated unit test.** Three-state machine (disconnect → wait → connect) is exercised indirectly via `test_failure_triggers_bounce` in `test_monitor_controller.py`, which uses a `FakeBounceOp`. Real `BounceOperation` is covered by live validation.

### Known follow-ups (out of scope)

- Remove the now-redundant `threading.Lock` in `MetricsCollector` (spec-declared non-goal).
- Rename `main_window.monitor_thread` → `main_window.monitor` (see above).
- Consider switching `widgets.py`/`tray.py` sync VPNManager calls to their async variants on future passes — one-shot user-initiated operations, so lower priority.

## Validation Report

To be written on completion of live validation (`validation-reports/YYYY-MM-DD-spec-009-event-driven-monitor.md`).
