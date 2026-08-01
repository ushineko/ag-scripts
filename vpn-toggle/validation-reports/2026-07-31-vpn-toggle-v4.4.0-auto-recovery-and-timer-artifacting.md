## Validation Report: Auto-Recovery for a Down VPN + Connection-Timer Artifacting (v4.4.0)
**Date**: 2026-07-31 15:30
**Commit**: pre-commit
**Status**: PASSED — spec 010 complete, counter render artifact resolved

Covers two user-reported bugs:

1. **Reconnects give up too soon when the retry itself times out** — implemented as [`specs/010-monitor-recover-down-vpn.md`](../specs/010-monitor-recover-down-vpn.md).
2. **The "connected" timer in the GUI flashes to a default or cached value between per-second updates.**

### Phase 3: Tests

- Test suite: `/usr/bin/python3 -m pytest tests/` (from `vpn-toggle/`)
- Results: **248 passing, 0 failing** (baseline before this work: 195)
- New coverage (+53):
  - `TestAutoRecovery` (18) — down VPN triggers a connect; failed reconnect schedules a retry; backoff grows and is capped (`[30, 60, 120, 120, 120, 120]` at a 120s ceiling); a 500-attempt outage stays capped rather than overflowing; success resets the backoff; an outage never increments `failure_threshold` and never emits `vpn_disabled`; a user disconnect suppresses recovery and a user reconnect lifts it; per-VPN `auto_recovery` overrides the global toggle in both directions; ticks during backoff do not launch a second connect; `stop()` cancels pending recovery.
  - `TestStatusProbeResilience` (3), `TestAsyncStatusSweep` (4), `TestConnectionTimerPrecision` (1), `TestAutoRecoverySettings` (3), `TestRecoveringCardDisplay` (3).
  - `TestRecoveryOnlyRestoresWhatWasUp` (4) — a VPN already down at startup is never auto-connected; one that drops after being seen up is recovered.
  - `TestCounterRenderStability` (5) — the counter font is point-sized not px-sized, digits are equal width, the label width is fixed across values, the background is opaque, and the text format is `PlainText`.
  - `TestActivenessProbeOk` (6) — `probe_ok` distinguishes command failure from a genuinely down VPN in both backends.
  - `TestSessionCreatedTimestamp` (5) — openvpn3 `Created:` parsing, including the trailing-`PID:` column layout and an unparseable value degrading to `None`.
- Contract change: `test_sets_idle_when_not_connected` asserted the exact behavior spec 010 exists to remove (down → `IDLE`). Rewritten as `test_down_vpn_enters_recovery_not_idle`; the old assertion is retained as `test_sets_idle_when_not_connected_and_recovery_disabled` for the opt-out path.
- Status: PASSED

### Phase 3b: Live measurement (bug 2)

Unit tests cannot show event-loop stalls, so the GUI was instrumented and run
window-less against the real backends for 95s before and after the fix
(monitor disabled, isolated config — no VPN state was changed).

| Metric (95s run, 3 VPN cards, 1 connected) | Before | After |
|---|---|---|
| Blocking `is_vpn_active` calls on the GUI thread | 117 | 3 (construction only) |
| Main-thread block per 5s status cycle | ~95–100 ms | not measurable |
| Counter updates off the 1s cadence by >10 ms | 41 / 95 | 1 / 94 |
| Worst cadence deviation | 137 ms | 73 ms (single startup outlier) |

Root causes found, all three fixed:

- `update_all_vpn_status()` ran one blocking `nmcli`/`openvpn3` call per card, and
  `TrayManager.update_tooltip()` then re-probed every VPN a second time — six
  blocking subprocess calls every 5s. Replaced with a single async probe per VPN
  feeding both the card and the tooltip.
- The 1s counter used Qt's default `CoarseTimer`, which is permitted to drift the
  interval by up to 5%; measured ticks ranged 0.978–1.137s. Now `PreciseTimer`.
- Both the 5s sweep and the 1s tick wrote the same label, so the sweep advanced
  the display off-cadence. The sweep now paints the counter only on the connect
  transition; the 1s tick is the sole steady-state writer.

Two further defects in the same path were fixed by inspection (the openvpn3
tunnel `aiqlabs` was down at the time; both were verified live later the same
day — see Phase 3d):

- `is_vpn_active` returns `False` both when a VPN is down and when the backend
  command errors or times out. The card treated the latter as a disconnect,
  blanking it and discarding `_connected_since` — so the uptime restarted from
  zero on the next good probe. Ops now carry `probe_ok`.
- `OpenVPN3Backend.get_connection_timestamp()` returned `None` unconditionally,
  so the GUI stamped `datetime.now()` and every openvpn3 card's uptime counted
  from when the GUI first noticed the session rather than from the real connect
  time. It now reads the session's `Created:` field.

- Status: PASSED

### Phase 3c: Counter render artifact — RESOLVED

**Symptom.** In ~10% of frames the uptime counter rendered coarse and
un-antialiased: same glyphs at the same positions, blocky edges. At a glance it
read as garbled digits (the user described it as "all 2s"). Only the label that
repaints every second was affected; static text on the same row was always crisp.

**Cause: `QT_WAYLAND_DISABLE_FRACTIONAL_SCALE=1`, which this work had itself
added earlier in the session as a speculative fix.** With it set, Qt renders the
window at integer 2x and KWin downscales to the output's 1.5x. Resampling the
label's small per-second partial repaint is what produced the coarse glyphs.
Without it Qt renders natively at 1.5x and there is no resample.

**Measurement.** Lossless PNG bursts, identical crop and analysis, deviation of
the static `00:03:` prefix from the per-run median:

| Configuration | Artifacted | Max deviation |
|---|---|---|
| A — env var set, redundant repolishes | 3/30 | 8.57 |
| B — env var set, repolishes guarded | 3/30 | 8.57 |
| C — env var reverted, repolishes guarded | 0/30 | 0.03 |
| D — repeat of C | 0/30 | 0.02 |

B isolates the repolish guard: still 3/30, so the guard was not the operative
change. C/D isolate the env var: 0/60 combined vs 6/60 with it set
(Fisher's exact p ≈ 0.03). The user independently confirmed the artifact
disappeared at the same point.

**Process notes, recorded so the mistakes are not repeated:**

- The env var was originally adopted on a 0/14 sample against a ~10% base rate —
  a result with a ~23% chance of occurring by luck. Fourteen frames was far too
  small a sample to conclude from, and it led to a wrong fix being shipped into
  the systemd unit and documented as verified.
- A user-supplied screencast (`Screencast_20260731_211122.webm`) showed the
  artifact but was unusable as evidence: VP9 at ~3 Mbps over a 6000x3840 canvas,
  where the garbling has an encoder signature (onset exactly on the repaint
  frame, 2-3 frames long, then clean, while clean-frame deviation converges
  2.26 → 0.25 across the clip). Lossless PNG bursts were the reliable instrument.
- Sporadic artifacts were also observed before the env var existed (1/7, 1/14),
  so it is not certain the env var explains the original report. What is
  established is that the shipped build measures clean over 60 frames and the
  reporter confirms the symptom is gone.

**Kept regardless of the artifact** (all measured neutral, retained on merit):
point-sized fixed-pitch `QFont` instead of a stylesheet `font-size: 10px`,
opaque background, fixed width, `PlainText` format, and the `_set_style` guard
that stops re-applying identical stylesheets 12x per card per minute.

- Status: RESOLVED

### Phase 3d: OpenVPN3 live verification

`aiqlabs` was brought up at 21:04:47, allowing the `Created:` parser to be
checked against real `openvpn3 sessions-list` output rather than only the test
fixtures. Real layout, confirmed verbatim:

```
     Created: 2026-07-31 21:04:47                       PID: <pid>
```

`%Y-%m-%d %H:%M:%S` with a trailing `PID:` column — the first format in
`_CREATED_FORMATS`, and the trailing-column case already covered by
`test_parse_sessions_created_with_trailing_pid_column`. Live results:

- `_parse_sessions_output` returned `created=datetime(2026, 7, 31, 21, 4, 47)`,
  plus the correct `config_name`, `status`, and `device`. The real output also
  carries a `Connected to:` line absent from the fixtures; it parses harmlessly.
- `get_connection_timestamp('aiqlabs')` returned that timestamp rather than
  `None`, so the GUI no longer falls back to `datetime.now()`.
- **End-to-end proof**: the app was restarted at 21:06:33 with the session still
  up. The `aiqlabs` card then showed `00:00:02:05` — measured from the session's
  real start, not from the ~19s-old app process. The pre-fix behavior would have
  shown `00:00:00:19` and counted up from zero on every restart.
- Eight consecutive captured frames of the openvpn3 card's counter ticked
  `02:25` → `02:32` with no render artifacts, matching the NM card.
- The monitor's ping assert against the tunnel passed (72.3ms).

- Status: PASSED

### Phase 4: Code Quality

- **Duplication removed**: `OpenVPN3Backend._parse_sessions` was a verbatim copy of the module-level `_parse_sessions_output`. The method now delegates, so the new `Created:` parsing exists once instead of twice.
- **Dead code**: none introduced. No orphaned imports (`Optional` was already imported in `tray.py`; `datetime` already in `openvpn3.py`).
- **Encapsulation**: recovery logic is six small single-purpose methods on `MonitorController` (`_handle_down`, `_start_recovery`, `_on_recovery_done`, `_recovery_delay_seconds`, `_schedule_recovery_retry`, `_cancel_pending_recovery`/`_clear_recovery_state`), each well under the 50-line guideline and mirroring the existing bounce/session op pattern.
- **Overcomplication check**: backoff state is three plain dicts plus a set, matching how `_active_sessions` / `_active_bounces` are already tracked. No new abstraction layer.
- **Spec 009 invariants preserved**: no blocking calls added to the main thread; every `QProcess`-backed op and `QTimer` is strong-referenced until its completion slot and cancelled in `stop()`.
- Status: PASSED

### Phase 5: Security Review

- **Phase A — Dependency CVE scan**: `pip-audit` 2.10.0 (`~/miniforge3/bin/pip-audit`). It audits the ambient conda base environment, not this project: vpn-toggle has no `requirements.txt`/`pyproject.toml`, and its third-party imports are `PyQt6`, `pyqtgraph`, `numpy`, and `requests` (system packages). Findings reported — `pillow 12.1.0`, `pygments 2.19.2`, `pytest 9.0.2`, `soupsieve 2.8.3` — are pre-existing conda-env housekeeping in packages this project does not import at runtime. **Not introduced or affected by this diff.** No dependency was added.
- **Phase B — OWASP Top 10 (AI-assisted, best-effort — not compliance evidence)**: clean. All new subprocess work goes through existing `QProcess` argv paths (`nmcli`, `openvpn3`) with no shell and no new user-controlled arguments — the recovery path reuses `connect_vpn_async`, whose argv was already `['connection', 'up', vpn_name]` with `vpn_name` sourced from local config. The new `Created:` parser is a regex over local CLI stdout with no deserialization. New log lines contain VPN names, attempt counts, and backoff intervals only.
- **Resource-exhaustion check** (relevant since this adds an automatic retry loop): backoff is bounded by `recovery_backoff_max_seconds` (default 600s); the exponent is capped at 30 before shifting so a multi-day outage cannot construct a huge integer; `_recovery_timers`/`_active_recoveries` guards prevent a tick from launching a parallel connect, and `stop()` cancels everything. Covered by `test_tick_does_not_launch_a_second_connect_during_backoff` and `test_long_outage_does_not_overflow_backoff`.
- **Phase C — Secrets & credential scan**: pattern scan over added lines for password/secret/token/api-key/private-key — 0 findings. The diff contains VPN names, hostnames, D-Bus session paths, and timestamp fixtures.
- Status: PASSED

### Phase 5.5: Release Safety

- **Change type**: code-only (monitor logic, GUI refresh path, backend parsing) plus additive config keys.
- **Rollback**: `git revert` of the v4.4.0 commit restores prior behavior in full. Alternatively, without reverting, set `monitor.auto_recovery = false` (or untick "Reconnect a VPN that is unexpectedly down" in Settings) to disable only the new recovery behavior.
- **Config compatibility**: the three new `monitor` keys are read with `.get(..., default)`, so an existing `config.json` written by v4.3.1 works unchanged and picks up the defaults. No migration, no on-disk format change. Metrics `*.jsonl` and all signal payloads are unchanged except `get_vpn_status()` gaining an additive `recovery_attempts` key.
- **Behavioral note**: a VPN that is down will now be reconnected automatically where it previously stayed down. This is the intended fix. Users who deliberately leave a monitored VPN down should disconnect it from the GUI (which suppresses recovery) rather than via `nmcli` directly, or set `auto_recovery: false` for that VPN.
- Status: PASSED

### Phase 6.5: Spec Reconciliation

`specs/010-monitor-recover-down-vpn.md` re-read and diffed against the
implementation. 11 of 12 acceptance criteria are met and checked.

**Manual E2E: PASSED** (run attended, with the user's approval, 2026-07-31 17:52).
v4.4.0 was installed and started under systemd, then `infra_pc` was dropped with
`nmcli connection down infra_pc` at 17:52:02:

```
17:52:30 WARNING: infra_pc: VPN is down, starting auto-recovery
17:52:30 INFO:    infra_pc: recovery attempt 1
17:52:32 INFO:    Connected to infra_pc
17:52:32 INFO:    infra_pc: auto-recovery succeeded
```

Detected within one 30s check interval, reconnected in 2s. `git.attackiq.com`
resolution returned to `100.x` and normal assert cycles resumed at 17:53:00.
Spec 010 acceptance criteria are now all met.

A cold-start hazard was found and fixed while installing: the user-disconnect
suppression set is in-memory, so on a fresh start every configured, enabled but
down VPN (`us_las_vegas`, `aiqlabs`) would have been auto-connected. Recovery is
now scoped to tunnels the monitor has observed connected. Verified before
restarting by dry-running the monitor against the real config with all
state-changing backend calls blocked: zero connection attempts, both down VPNs
left `IDLE`. Confirmed again on the live service — neither was touched.

The design decision the spec flagged for confirmation at implementation time
(manual-disconnect vs outage-down) was implemented as the spec's own stated
assumed mechanism: a per-VPN user-disconnect suppression flag, set by
`notify_user_disconnected()` and cleared by `reset_vpn_state()` or by observing
the VPN connected. The rejected alternatives were not used.

### Overall

- All quality gates passed: YES
- Spec 010 status: COMPLETE (all acceptance criteria met, manual E2E passed attended)
- Version: 4.3.1 → 4.4.0
