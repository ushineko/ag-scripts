# Spec 033: the lighting startup race has two halves, and OK can mean partial

> **Note**: This work has no associated issue tracker ticket. Consider creating one for traceability.

## Executive Summary

After a reboot, scenes reached only the GPU. Two caches were poisoned by the same
early start: `openrgb-server` enumerated 2 of 6 devices, and the monitor then
cached *that* list. Both needed manual restarts. The gate now waits for every RGB
device to be enumerable and accessible, and the monitor retries until every scope
entry is matched. Reviewers should look at `unmatched_scope_entries` and at why
`lighting_health` could not have caught this.

## Context

Spec 026 fixed "OpenRGB started before the hardware existed" by making the unit
wait for the Kraken. On 2026-09-17 the same failure recurred with that gate in
place, because the gate was keyed on the wrong thing.

Measured on the failing boot: machine up at 09:54:45, `openrgb-server` started at
09:55:01 — 16 s later — with `Starting` and `Started` in the same second. The
Kraken-wait passed immediately. OpenRGB still enumerated only the GPU and the
keyboard: no motherboard, no Kraken, no MM700, no receiver.

**Waiting on one device says nothing about the others.** The Kraken is not what
arrives last, so gating on it is close to not gating at all.

The second half is worse, because it is silent by construction. The monitor
primed its device list on two fixed timers (5 s and 12 s), sized against the ~9 s
OpenRGB detection takes *from its own service start* — an assumption that the
server is already running. It cached the 2-device list, found one in scope
(`geforce`), and `lighting_health` reported:

```
lighting_ready  detail="1 device(s) in scope"
```

`LIGHTING_OK`. One matched device is enough. Nothing above that layer could tell
a whole list from a partial one, so scenes silently skipped the motherboard for
the rest of the session and the fan stayed dark.

## Requirements

1. The server must not start until every RGB device it needs is enumerated.
2. Presence is not sufficient — the node must be usable by the server's user.
3. The gate must never be a hard dependency: a machine missing a device still
   gets a lighting server, with the absence reported.
4. The monitor must not cache a partial device list for the session.
5. The monitor's startup wait must not assume a fixed delay, since the thing it
   waits for is now itself gated on hardware.
6. A partial list must be distinguishable from a whole one in the logs.

## Acceptance Criteria

- [x] `openrgb-wait-for-devices.sh` waits for every USB RGB device in the
      lighting scope, by vendor:product, not for the Kraken alone.
- [x] It tests each matching hidraw node for read **and** write, because the node
      appears before logind applies the uaccess ACL.
- [x] On timeout it names the missing devices on stderr and exits 0, so the
      server still starts.
- [x] Verified in both directions: it passes in ~0.03 s with all devices present,
      and with a deliberately absent id it times out and names it.
- [x] `openrgb-server.service` uses the helper as its `ExecStartPre`.
- [x] `unmatched_scope_entries()` returns scope entries with no matching device.
- [x] The monitor retries priming until that set is empty, or a deadline passes.
- [x] On the deadline it logs `lighting_degraded` naming what is missing.
- [x] A test asserts a partial list still reports `LIGHTING_OK`, documenting why
      a health check alone cannot catch this.
- [x] That test pins `server_alive`, so it does not depend on a live server.
- [x] Verified live: with OpenRGB stopped, the monitor retried rather than
      caching; on starting the server it recovered to 4 devices unaided.
- [x] Existing tests still pass.

## Risks & Assumptions

- **The expected-device list is hardcoded to this machine.** Hardware changes
  need an edit; the timeout path keeps that from being fatal.
- **The gate can now delay the server by up to 90 s**, which makes the monitor
  more likely to start first — which is exactly why the monitor half had to be
  fixed in the same change rather than later.
- **The deadline is 150 s.** Past that a genuinely absent device would otherwise
  retry forever.
- **Rollback**: revert both commits (ag-scripts and dotfiles). The gate returns
  to the Kraken-only wait and the monitor to fixed timers.

## Alternatives Considered

- Considered ordering the monitor after `openrgb-server` with a systemd
  dependency; rejected because the monitor is launched from XDG autostart, and
  the retry is needed anyway for the case where OpenRGB restarts mid-session.
- Considered having `lighting_health` treat a partial list as degraded; rejected
  because a machine may legitimately lack a scoped device, and that would report
  a permanent false alarm. Completeness matters during startup, not forever.

## Status: COMPLETE
