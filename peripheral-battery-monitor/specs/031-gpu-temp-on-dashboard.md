# Spec 031: GPU temperature on the LCD dashboard

> **Note**: This work has no associated issue tracker ticket. Consider creating one for traceability.

## Executive Summary

The dashboard gains a third metric, GPU temperature, beside CPU and pump. It is
read from OpenLinkHub's `/api/gpuTemp` on the same poll that already fetches CPU
temperature. Reviewers should look at the metric-row geometry in
`aio_dashboard.py`, which had to move clear of the coolant ring to fit a third
column.

## Context

The dashboard showed CPU, coolant and pump. The GPU is the other heat source in
the loop's airflow path and the one the user watches during games, and it was the
obvious gap.

**Source choice.** The GPU has no hwmon node on this machine - there is no nvidia
entry under `/sys/class/hwmon` - so the options were a `nvidia-smi` subprocess per
poll or an HTTP endpoint on a daemon the monitor already polls. OpenLinkHub
exposes `/api/gpuTemp` with the same envelope as `cpuTemp`, so the existing
extractor and the existing async fetch both apply: one more parallel request
instead of a process spawn, degrading exactly as the CPU reading already does.

**Geometry.** The metric row was laid out from `_MARGIN = 40`. That is fine for
two columns but puts a third column's outer edges through the coolant ring - the
`RPM` unit label was drawn over the arc. The ring spans x 135..505 at the unit
row, so the row is inset to 140 and the fonts shrink at three columns, because a
44pt four-digit pump reading overflows a one-third column.

## Requirements

1. GPU temperature appears on the dashboard alongside CPU and pump.
2. It is read without spawning a process per poll.
3. A missing or failing GPU reading degrades like any other absent metric and does
   not break the snapshot, the alerting, or the rest of the dashboard.
4. The three-column row does not collide with the coolant ring at any value width.
5. GPU movement does not drive the push rate up.

## Acceptance Criteria

- [x] `aio_reader.endpoint_urls()` returns a `gpu` endpoint alongside `cpu` and
      `devices`, and the existing test asserting endpoint keys match
      `build_snapshot()`'s arguments covers it.
- [x] `build_snapshot()` accepts `gpu_json` and emits `gpu_temp_c`, reusing the
      CPU extractor because the envelope is identical.
- [x] A missing or unparseable GPU payload yields `gpu_temp_c = None` and leaves
      the rest of the snapshot intact.
- [x] `aio_section` fetches the GPU endpoint in the same parallel batch
      (`_inflight` pending count raised to 4) and passes it to `build_snapshot()`.
- [x] The dashboard draws three metrics - CPU, GPU, PUMP - with fonts sized per
      column count.
- [x] The metric row clears the coolant ring, verified by a test that computes the
      ring chord arithmetically rather than by eye, and checks the full column
      bounds rather than the rendered text width.
- [x] GPU temperature is thresholded in `should_push` on the same delta as CPU, and
      is part of `content_key`.
- [x] A successful LCD push logs the GPU value alongside coolant, CPU and pump.
- [x] Existing tests still pass.

## Risks & Assumptions

- **The reading depends on OpenLinkHub.** If that daemon is down the GPU metric is
  absent, exactly as the CPU metric already is. Cooling telemetry and pump alerting
  come from liquidctl and are unaffected.
- **`/api/gpuTemp` returning the same envelope as `cpuTemp` is observed, not
  documented.** The shared extractor is the bet; a shape change would surface as
  `gpu_temp_c = None`, which is a degraded metric and not a failure.
- **A GPU under load wanders continuously.** Keying the push gate on it at
  whole-degree precision would redraw the screen on essentially every sample, so it
  uses the same 5 C delta the CPU gate already documents.
- **Rollback**: revert the commit. The dashboard returns to two metrics at the
  original margin; no settings or on-disk state change.

## Alternatives Considered

- Considered `nvidia-smi` per poll; rejected because it spawns a process every
  cycle for a value already available over a socket the monitor keeps open.
- Considered dropping coolant from the row to keep two columns; rejected because
  coolant is the pump-health signal and the ring already presents it well.
- Considered relaxing the new geometry test when the render looked clean at an
  inset of 125; rejected - the render only passed because centred text is narrower
  than its column, so the code was widened to clear the column bounds instead. A
  long value can no longer grow into the ring.

## Status: COMPLETE
