# Spec 010: Auto-Recover a Fully-Down VPN

> **Ticket**: No associated ticket — this is a personal public repo with no issue tracker (per project `.claude/CLAUDE.md`).

**Status: INCOMPLETE**

## Context

The event-driven monitor introduced in [spec 009](009-event-driven-monitor.md) only health-checks VPNs that are *currently connected*. Once a tunnel is fully disconnected it becomes invisible to the monitor and is never brought back up. This produced a real ~15-hour outage on 2026-06-16:

1. ~01:35 a transient blip on the home uplink made the `infra_pc` DNS assert (resolve `git.attackiq.com`) time out.
2. `MonitorController` reacted correctly: failure count went to 1/3, and since `1 < failure_threshold(3)` it triggered auto-reconnect attempt 1 (`_start_bounce` → `bounce_vpn_async`), which **disconnects then reconnects**.
3. The reconnect timed out after 60s (`_on_bounce_done` failure path) because the uplink was still recovering.
4. Then nothing for ~15 hours. The bounce had left `infra_pc` disconnected, and from that point every 30s tick hit `_on_is_active` → `if not is_connected: state = IDLE; return` — a down VPN is silently ignored. The failure count never reached 3, so the tunnel was never even marked DISABLED; it was simply orphaned-down until a manual `nmcli connection up infra_pc`.

NetworkManager did not recover it either: `infra_pc` is a *secondary* of `Wired connection 1`, so NM only re-ups it when the parent ethernet connection re-activates. An upstream-only blip (link never drops) never fires that trigger, and the monitor's bounce had explicitly disconnected it.

Two design gaps combine:

- **`_on_bounce_done` failure path only logs** (`monitor.py:313-315`) — no retry, no backoff, no reschedule. One failed bounce and recovery stops.
- **The tick loop only acts on *connected* VPNs** (`_on_is_active`, `monitor.py:199-201`). There is no "this VPN should be up but is down → bring it up" path.

## Requirements

Make the monitor treat an **enabled VPN that is unexpectedly disconnected** as a recoverable condition and reconnect it, instead of only watching already-connected tunnels.

1. When a tick finds an enabled, monitored VPN that is not connected — and the disconnection was not user-initiated (see Risks & Assumptions) — the monitor attempts to (re)connect it.
2. Reconnect attempts use **bounded exponential backoff** (e.g. 30s → 60s → 120s → … capped at a configurable max such as 600s) so a sustained outage does not hammer `nmcli`/`openvpn3` every tick, and recovery resumes automatically once connectivity returns.
3. A failed bounce (`_on_bounce_done` failure) schedules the next recovery attempt under the same backoff policy rather than terminating recovery.
4. A connectivity-driven down state must **not** trip the `failure_threshold` "disable VPN" path. Disabling a VPN is appropriate for persistent assert failure on a *live* tunnel, not for an uplink outage. Outage recovery and assert-failure disabling stay distinct.
5. A reconnect that succeeds resets backoff and resumes the normal connected/grace/monitoring flow (existing `connection_times` / grace-period logic).
6. The behavior is opt-out-able via config (default on) so the user can disable auto-recovery per VPN or globally.

## Acceptance Criteria

- [ ] A new or extended `MonitorState` distinguishes "down / recovering" from `IDLE` and `DISABLED`.
- [ ] On a tick, an enabled VPN reported not-connected (and not user-disconnected) transitions to the recovering state and triggers a connect attempt, instead of returning silently in `IDLE` (`monitor.py:199-201`).
- [ ] `_on_bounce_done` failure path schedules the next recovery attempt (backoff) instead of only logging (`monitor.py:313-315`).
- [ ] Recovery uses bounded exponential backoff with a configurable cap; the backoff interval is logged on each attempt so the gap is observable in the journal (no silent stalls).
- [ ] A connectivity-driven down/recovering state does not increment toward `failure_threshold` and never calls `_disconnect_and_disable`.
- [ ] A successful reconnect resets the backoff counter and restores the connected → grace → monitoring flow.
- [ ] Config exposes an auto-recovery toggle (default enabled) honored by the monitor; documented in README monitor settings.
- [ ] A user-initiated disconnect (via the tray/GUI) suppresses auto-recovery for that VPN until the user reconnects or re-enables it — the monitor must not fight a deliberate manual disconnect. (See Risks & Assumptions for the chosen mechanism.)
- [ ] `tests/test_monitor_controller.py` gains coverage for: (a) enabled-but-down VPN → reconnect attempt; (b) repeated failed reconnects follow backoff (interval grows, capped); (c) successful reconnect resets backoff; (d) outage-down does not disable the VPN; (e) user-disconnected VPN is not auto-reconnected. Async/backend primitives are faked at the existing seams (fake `QProcess`/backend), consistent with spec 009.
- [ ] All existing tests across the suite continue to pass; `pytest tests/` is clean.
- [ ] **Manual end-to-end verification** (documented in the validation report, not CI — a real tunnel cannot run in CI): with `infra_pc` connected, manually disconnect it (`nmcli connection down infra_pc`) and confirm the monitor auto-reconnects it within the backoff window, restoring the internal `git.attackiq.com` (`100.80.0.0/12`) resolution. This exercises the real NetworkManager/openvpn3 downstream that the unit tests fake.

## Risks & Assumptions

- **Manual-disconnect vs outage-down is the load-bearing design decision** (flagged for confirmation at implementation time). The monitor must reconnect outage-induced down states but must not override a deliberate user disconnect. Assumed mechanism: track a transient per-VPN "user-disconnected" suppression flag set when the disconnect originates from the tray/GUI action (not from a monitor bounce), cleared on user reconnect / re-enable. Alternative mechanisms are listed below; confirm the choice before coding.
- **Backoff prevents a tight reconnect loop** during a sustained outage (could otherwise spawn an `nmcli`/`openvpn3` op every tick). Cap chosen so recovery latency after the outage clears stays bounded (≤ cap).
- **No persistent disabling on connectivity loss.** Requirement 4 keeps the existing `failure_threshold` disable semantics scoped to live-tunnel assert failure only; an outage must remain self-healing.
- **Rollback**: pure-logic change in `monitor.py` (+ small config/GUI wiring). Revert the commit, or set the new auto-recovery toggle to off, to restore prior behavior. No migration, no schema, no data movement.
- **Integration boundary**: the real downstream is NetworkManager / openvpn3 via `nmcli`/openvpn3 backends. CI fakes these (spec 009 pattern); the boundary is covered by the documented manual E2E step above rather than a mocked unit test alone.
- **Single-VPN behavior unaffected when connected**: when tunnels are healthy the tick path is unchanged; recovery logic only engages on the not-connected branch.

## Alternatives Considered

- **Reuse `enabled` as "desired connected" instead of adding a suppression flag** — rejected as the primary mechanism because `enabled` currently means "monitor this VPN," and `_disconnect_and_disable` already flips it to `False`; overloading it would conflate "stop monitoring" with "should be up," and a user's manual disconnect via the GUI would either be steamrolled or permanently stop monitoring. A dedicated user-disconnect suppression flag keeps the two concepts separate. (Confirm at implementation.)
- **Immediate fixed-interval retry (every tick) instead of backoff** — rejected; hammers the VPN backends during a multi-minute outage and risks accept-queue / session-manager churn for no faster recovery.
- **Rely on NetworkManager autoconnect / `connection.secondaries`** — rejected as insufficient; it only re-ups the secondary when the parent ethernet reactivates, which does not happen for upstream-only outages (the exact 2026-06-16 failure mode).

## Technical Notes

- Touch points: `vpn_toggle/monitor.py` (`_on_is_active` not-connected branch ~`199-201`, `_on_bounce_done` failure path ~`313-315`, `MonitorState` enum ~`25-31`, `_start_bounce`/tick scheduling). Config defaults in `vpn_toggle/config.py` (`DEFAULT_CONFIG['monitor']`: `check_interval_seconds`, `grace_period_seconds`, `failure_threshold`) — add the auto-recovery toggle and any backoff-cap setting here. Reconnect uses the existing `VPNManager.bounce_vpn_async` / `connect_vpn_async`.
- Keep the event-driven invariants from spec 009: no blocking calls on the main thread; every `QProcess`/`QDnsLookup`/`QNetworkReply` strong-referenced until its completion slot; backoff scheduled via `QTimer.singleShot`, cancelled cleanly in `stop()`.
- The GUI/tray should reflect the recovering state (existing `status_changed` signal) so a down/recovering VPN is visible rather than silently idle.
- Version bump (currently 4.3) + README monitor-settings + changelog update belong to the finalization pass, not this spec draft.

## Executive Summary

<!-- POPULATE LAST, at PR time (Phase 6.5). -->

## Status: INCOMPLETE
