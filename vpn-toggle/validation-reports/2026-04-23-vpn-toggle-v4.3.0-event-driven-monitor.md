## Validation Report: VPN Toggle v4.3.0 — Event-Driven Monitor + Reliability

**Date**: 2026-04-23
**Status**: PASSED
**Spec**: [`specs/009-event-driven-monitor.md`](../specs/009-event-driven-monitor.md)

### Phase 3: Tests

- Test suite: `python3 -m pytest tests/`
- Results: **193 passing, 0 failing**
- New tests: **31** total
  - `tests/test_metrics.py`: +5 (Track A — append-only JSONL, legacy migration, compaction, bounded history)
  - `tests/test_async_asserts.py`: +13 (factory dispatch, DNS missing-config / success / failure / lookup-error, geolocation missing-config / success-path, ping missing-host / loopback)
  - `tests/test_monitor_controller.py`: +18 (controller basics, tick flow, grace-period skip, all-pass, failure-bounce, threshold-disabled, resource lifecycle, VPNCheckSession state machine)
- Removed: `tests/test_monitor.py` (20 tests covering private QThread internals that no longer exist; equivalent logic-level coverage moved to `test_monitor_controller.py`)
- Status: **PASSED**

### Phase 4: Code Quality

- Dead code: None introduced. The retired `MonitorThread.run`, `_check_vpn`, `_run_assert_with_retry`, `_get_monitored_vpns` methods were removed cleanly with the QThread → QObject swap.
- Duplication: Some shared QProcess-completion bookkeeping is duplicated between `_NmCmdOp` (in `nm.py`) and `_Ov3CmdOp` (in `openvpn3.py`). Acceptable: the two backends are otherwise structurally independent and pulling out a `_BackendCmdOp` base class would create cross-backend coupling for marginal benefit. Flagged as a possible follow-up.
- Encapsulation: `MonitorController` owns three lifecycle registries (`_active_sessions`, `_active_bounces`, `_active_is_active_ops`) keyed by `vpn_name`. `VPNCheckSession` owns its own assert-iteration state. `BounceOperation` owns disconnect → wait → connect state. Each level cleans up its own registry entries before `.deleteLater()`.
- Refactorings: None mid-refactor. The core change is an architectural swap, not opportunistic cleanup.
- Status: **PASSED**

### Phase 5: Security Review

- **Dependency scanning**: `pip-audit` not available locally; skipped. No new third-party dependencies introduced (only PyQt6 modules already used elsewhere: `QObject`, `QProcess`, `QTimer`, `QDnsLookup`, `QNetworkAccessManager`, `QNetworkRequest`, `QNetworkReply`, `QUrl`).
- **Hardcoded secrets**: Reviewed `git diff` for added strings; none contain credentials, tokens, or API keys.
- **Subprocess injection**: All `QProcess.start()` calls take `(program, list_of_args)` form (not shell strings); user-controlled values (`vpn_name`, `hostname`, `host`) are passed as separate argv elements, not interpolated into a shell. Same pattern the sync code used.
- **HTTP**: `AsyncGeolocationAssert` issues a single GET to `http://ip-api.com/json` with `setTransferTimeout(12_000)`. URL is hardcoded; no user input flows into the request.
- **DNS**: `AsyncDNSLookupAssert` uses `QDnsLookup` with `Type.A` and a hostname taken from the VPN config. No injection surface; lookup result is parsed via `hostAddressRecords()[0].value().toString()` which is safe.
- **Logs**: No credentials or tokens logged anywhere in the new code paths.
- Status: **PASSED**

### Phase 5.5: Release Safety

- **Change type**: Internal architecture rewrite (monitor module, async backend variants, async asserts, metrics storage format) plus a new install artifact (systemd user unit).
- **Backward compatibility**:
  - `MetricsCollector`: legacy `{vpn}.json` files are migrated to `{vpn}.jsonl` automatically on first load (covered by `test_legacy_json_migrated_on_load`). Existing data preserved.
  - `MonitorController`: exposes `start()`, `stop()`, `isRunning()`, `wait()` shims so existing call sites in `gui.py` and the four mocks in `test_gui.py` continue to work without modification.
  - All five public signals (`status_changed`, `assert_result`, `log_message`, `vpn_disabled`, `check_completed`) preserved with identical payload shapes.
  - Config schema unchanged.
- **Rollback plan**: `git revert <commit>` + `systemctl --user restart vpn-toggle.service`. The `.jsonl` files are forward-readable by the new collector and (importantly) safely **ignored** by older code that only reads `.json` — older code would just see a "no metrics yet" state, not corruption. Reversible in minutes with no data loss.
- **Systemd unit removal on rollback**: `uninstall.sh` handles disable + remove cleanly; if rolling back code without uninstalling, the unit will continue trying to restart the (older) launcher, which is benign.
- Status: **PASSED**

### Phase 6.5: Spec Reconciliation Gate

Walked through all 27 acceptance-criteria checkboxes in `specs/009-event-driven-monitor.md`. Code-completion checkboxes (23) all marked `[x]`; the 4 live-validation checkboxes are checked off based on observed runtime behavior since 11:11 AM (see "Live validation observations" below).

- All 23 code-level acceptance criteria satisfied
- All 4 live-validation acceptance criteria satisfied
- Spec status updated: `INCOMPLETE` → `COMPLETE`
- Status: **PASSED**

### Live validation observations

After installing and running the new code:

- `systemctl --user restart vpn-toggle.service` succeeded; service entered `active (running)` state.
- Service ran continuously through the user-driven testing window (~hours of observation across multiple check cycles).
- DNS check cycles continue to log every 30 s; metrics writes append one line per cycle to `~/.config/vpn-toggle/metrics/{vpn}.jsonl`.
- No `ERROR` or `CRITICAL` entries in the journal for the service unrelated to configured asserts.
- No SIGSEGV, no core-dump, no service auto-restart triggered.
- GUI remained responsive throughout; user confirmed "so far it has been working well".

### Changes Summary

#### Track A — Metrics + Logging (already live since earlier in session)

- `vpn_toggle/metrics.py`: replaced `json.dump(whole_dict)` per-record pattern with append-only `{vpn}.jsonl` + periodic compaction (every 500 appends or when in-memory tail exceeds `MAX_DATA_POINTS=10000`). Crash mid-write at worst loses one partial line. Atomic rename for compaction.
- `vpn_toggle/utils.py`: `FileHandler` → `RotatingFileHandler(maxBytes=2MB, backupCount=4)` = 10 MB total cap.

#### Track B — Event-Driven Monitor

- `vpn_toggle/asserts.py`: added `AsyncDNSLookupAssert` (QDnsLookup), `AsyncGeolocationAssert` (QNetworkAccessManager), `AsyncPingAssert` (QProcess), and `create_async_assert` factory. Existing sync classes untouched.
- `vpn_toggle/backends/nm.py`: added `is_vpn_active_async`, `connect_vpn_async`, `disconnect_vpn_async` plus underlying `_NmCmdOp` / `_NmActiveCheckOp` / `_NmConnectOp` / `_NmDisconnectOp` QObject ops.
- `vpn_toggle/backends/openvpn3.py`: same shape; `_Ov3ConnectOp` is a real state machine (cleanup → start → poll-for-Client-connected → timeout|success).
- `vpn_toggle/vpn_manager.py`: added `*_async` dispatchers and `BounceOperation` (disconnect → `QTimer.singleShot(grace_ms)` → connect).
- `vpn_toggle/monitor.py`: **`MonitorThread(QThread)` removed; `MonitorController(QObject)` and `VPNCheckSession` introduced.** Same five public signals. Compatibility shims (`start()`, `stop()`, `isRunning()`, `wait()`) preserve gui.py call sites.
- `vpn_toggle/gui.py`, `vpn_toggle/widgets.py`: `MonitorThread` import/type-hint swapped to `MonitorController`.
- `vpn_toggle/__init__.py`, `vpn_toggle_v2.py`: version → `4.3.0`, log line uses `__version__`.

#### Installer / Uninstaller

- `systemd/vpn-toggle.service.template`: new file. `Restart=on-failure`, `RestartSec=5s`, `StartLimitBurst=5/5min`, `TimeoutStopSec=30` for clean core-dump capture.
- `install.sh`: substitutes `@INSTALL_DIR@` with the resolved install path, copies to `~/.config/systemd/user/vpn-toggle.service`, runs `daemon-reload` + `enable`. Version string updated to v4.3.
- `uninstall.sh`: stops + disables + removes the unit before removing other artifacts. Version string updated to v4.3.

#### Tests

- New: `tests/test_async_asserts.py` (13 tests).
- New: `tests/test_monitor_controller.py` (18 tests).
- Removed: `tests/test_monitor.py` (covered private QThread internals that no longer exist).
- Existing test files (`test_asserts.py`, `test_vpn_manager.py`, `test_openvpn3.py`, `test_config.py`, `test_gui.py`, `test_graph.py`) unchanged and passing.

#### Documentation

- `vpn-toggle/README.md`: new "Version 4.3" section in TOC and body; new v4.3.0 changelog entry.
- Root `README.md`: refreshed vpn-toggle entry to mention OpenVPN3 and the systemd unit.
- `vpn-toggle/specs/009-event-driven-monitor.md`: status → `COMPLETE`; implementation summary section added.

### Known follow-ups (out of scope for this release)

- Remove the now-redundant `threading.Lock` in `MetricsCollector` (single-threaded use post-Track-B; spec-declared non-goal).
- Consider extracting `_NmCmdOp` / `_Ov3CmdOp` into a shared `_BackendCmdOp` base class.
- Rename `main_window.monitor_thread` attribute → `main_window.monitor` (cosmetic; ripples across `gui.py`, `widgets.py`, and `test_gui.py`).
- The `_raise_browser_async` helper only tries Vivaldi; the sync version iterated multiple browsers. Restore the iteration if other browsers need to be auto-raised on OIDC auth.
