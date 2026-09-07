# Spec 017: AIO Stats Section

> **Note**: This work has no associated issue tracker ticket. This is a personal
> public repository with no issue tracker (see `.claude/CLAUDE.md`).

## Status: COMPLETE

## Executive Summary

Adds an AIO section to the monitor showing CPU temperature, coolant temperature
with a 5-minute sparkline, and fan/pump speeds, read from the OpenLinkHub daemon.
Two new modules: `aio_reader.py` (pure parsing plus a debug CLI) and
`aio_section.py` (the widget, fetching over `QNetworkAccessManager`). The section
stays hidden until the daemon reports something, so a machine without OpenLinkHub
is unaffected, and it keeps its last values dimmed when a working daemon goes
away. Review the degradation paths in `aio_section.render_snapshot` and the
channel classification in `aio_reader._extract_cooler` first. The section is
read-only on purpose: fan and pump duty writes are silently discarded by this
cooler's firmware.

## Context

The monitor already renders three stacked sections: the two-slot battery grid,
the bandwidth section, and the Claude usage section. This spec adds a fourth, **AIO**, showing liquid-cooler thermals sourced from
the OpenLinkHub daemon already installed on this machine.

OpenLinkHub (`openlinkhub` 0.9.1-3, AUR) runs as `openlinkhub.service` and
exposes a localhost-bound HTTP API on `http://127.0.0.1:27003`. It is the only
data source used here. Devices that OpenLinkHub cannot open or does not support
are out of scope, and nothing else (`liquidctl`, `sensors`, sysfs `hwmon`) is
consulted.

Background on the hardware and on OpenLinkHub's quirks is recorded in
`~/git/sysadmin/runbooks/aio-coolant-overtemp-and-commander-st-fan-control.md`.
Two points from that runbook shape this spec:

- **Coolant temperature is the number that matters.** The pump-head
  over-temperature alarm tripped at 57.1 °C and cleared near 50 °C, and coolant
  moves slowly enough to be worth trending. CPU package temperature on this
  i9-14900K spikes to 100 °C during normal boost without meaningful throttling,
  so it is displayed but not colour-graded.
- **Fan and pump duty cannot be written** on Commander ST firmware 2.x by either
  OpenLinkHub or liquidctl. This section is therefore **read-only**. No control
  affordances are added, and none should be added later without re-testing the
  runbook's A/B duty check.

### Observed API shape (captured live, 2026-09-06)

```
GET /api/cpuTemp   -> {"code":200,"status":1,"data":"98.0 °C"}
GET /api/gpuTemp   -> {"code":200,"status":1,"data":"48.0 °C"}
GET /api/devices/  -> {"code":200,"status":0,"devices":{ "<serial>": {
                        "Product":"iCUE COMMANDER Core",
                        "GetDevice":{"devices":{
                          "0":{"description":"AIO","name":"H150i ELITE LCD",
                               "rpm":2399,"temperature":45.8,
                               "HasSpeed":true,"HasTemps":true},
                          "1":{"description":"Fan","name":"Fan 1","rpm":1469,
                               "temperature":0,"HasTemps":false}, ... }}}}}
```

Three traps in that shape, each of which the reader must handle explicitly:

1. **`status` semantics differ per endpoint.** `/api/cpuTemp` returns
   `status:1` on success; `/api/devices/` returns `status:0` on success. The
   reader must not gate `/api/devices/` on `status == 1`. It gates on the
   presence of a populated `devices` object.
2. **Pseudo-devices exist.** `/api/devices/` includes a `"cluster"` entry whose
   `GetDevice.devices` is empty. Devices with no channels are skipped.
3. **Temperatures are pre-formatted strings with a unit.** `/api/cpuTemp`
   returns `"98.0 °C"`, and the daemon's dashboard has a `celsius` toggle, so
   `"208.4 °F"` is reachable. The reader parses value + unit and normalises to
   Celsius.

## Requirements

### R1 — Data layer: `aio_reader.py`

A new module following the `bandwidth_reader.py` precedent: plain dicts in,
plain JSON-serialisable dicts out, no Qt imports, CLI entry point for debugging.

- `build_snapshot(cpu_json, devices_json) -> dict` — **pure**, no I/O. Takes the
  two already-decoded API responses (either may be `None`) and returns the
  snapshot below. This is the only place parsing lives, and it is what the UI
  calls after its own async fetch.
- `read_aio(base_url=..., timeout=...) -> dict` — synchronous convenience
  wrapper: fetches both endpoints with `urllib`, calls `build_snapshot`. Used by
  the CLI and by tests; **not** used by the UI (see R2).
- `--json` CLI mode prints the snapshot to stdout, logs to stderr.

Snapshot shape:

```python
{
  "available": bool,        # True iff at least one displayable metric was read
  "error": str | None,      # short reason when available is False
  "timestamp": float,
  "cpu_temp_c": float | None,
  "coolant_temp_c": float | None,
  "coolant_label": str | None,   # e.g. "H150i ELITE LCD"
  "pump_rpm": int | None,
  "fans": [{"name": str, "rpm": int}, ...],   # possibly empty
}
```

Channel classification, device-agnostic (no serial or product string is
hardcoded):

- **Coolant / pump** — the first channel with `description == "AIO"`. Its
  `temperature` is coolant, its `rpm` is pump speed. Falls back to any channel
  with `HasTemps` true and a non-zero temperature when no `AIO` channel exists.
- **Fans** — every channel with `description == "Fan"` and `HasSpeed` true,
  across all devices, in channel order. A fan reporting 0 rpm is kept (zero-RPM
  mode is a real state), but excluded from the average.
- A temperature of exactly `0` on a channel is treated as "not reported", not as
  0 °C. OpenLinkHub uses 0 as the null value for fan channels.

### R2 — UI layer: `aio_section.py`

A self-contained `QFrame` mirroring `BandwidthSection`'s public API
(`set_visible`, `update_style(alpha, font_scale)`), owning its own timer.

**Transport.** The section fetches over `QNetworkAccessManager`
(`PyQt6.QtNetwork`) with a 2 s transfer timeout, not `urllib` on the GUI thread
and not a `QThread`. Rationale: two blocking HTTP calls per poll on the GUI
thread would freeze the widget for up to 2×timeout if the daemon hangs, and
`QThread` + `QObject` worker carries the GC hazards this project has already
been bitten by (spec 010). `QNetworkAccessManager` is event-loop native.
Nothing to orphan. Parsing stays in `aio_reader.build_snapshot`.

**Layout** (three rows plus a graph, matching the widget's existing density):

```
┌ AIO ─────────────────────────┐
│ CPU      98 °C               │
│ Coolant  45.8 °C             │
│ Fans     1405 rpm  pump 2399 │
│ ▁▁▂▂▃▄▅▆▆▅▄▃▂▂▁▁▁▂▃▄▅▆▇█▇▆▅▄ │
└──────────────────────────────┘
```

- **CPU** — `/api/cpuTemp`, one decimal, not colour-graded (see Context).
- **Coolant** — AIO channel temperature, one decimal, colour-graded against the
  runbook's observed thresholds: green below 50 °C, amber 50–55 °C, red at or
  above 55 °C (the runbook's stated warning band; the alarm itself tripped at
  57.1 °C).
- **Fans** — mean rpm across reporting fans, with the fan count and pump rpm as
  secondary text. Rounded to whole rpm.
- **Sparkline** — one shared, full-width plot of **coolant temperature only**,
  60 samples at a 5 s cadence = a 5 minute window. Drawn with `QPainter` in a
  small custom `QWidget`; no new dependency. It takes the colour of the current
  coolant band, and its vertical range auto-scales to the visible samples with a
  minimum span of 5 °C so an idle flat line does not render as noise.

**Rows for metrics that are absent are hidden**, so a Commander PRO with fans
but no AIO channel shows CPU + Fans and no coolant row or sparkline.

### R3 — Graceful degradation

The section must cost nothing on a machine with no OpenLinkHub, and must
self-heal if the daemon is restarted.

- **Never available** (daemon down, not installed, no supported device): the
  section stays hidden and the window is the size it is today. Polling
  continues at a slow 30 s cadence so a later `systemctl start openlinkhub`
  brings the section in without an app restart.
- **Was available, now failing**: the section stays visible with the last known
  values dimmed and `(unavailable)` appended to the header, following the
  bandwidth section's `(missing)` precedent. Sparkline history is retained.
  Recovery restores normal rendering; no gap is interpolated into the graph.
- **Partial data**: any metric that reads as `None` hides its own row; the
  section stays up as long as one metric is displayable.
- A failed poll never stops the timer and never raises into the event loop.

### R4 — Integration into `peripheral-battery.py`

- Constructed unconditionally in `initUI`, placed between the bandwidth section
  and the Claude section.
- New setting `aio_section_enabled`, default `True`, persisted in
  `~/.config/peripheral-battery-monitor.json`.
- Context menu: an **AIO** submenu with a checkable *Show AIO Section* item,
  alongside the existing Bandwidth submenu. Read-only: no fan/pump controls.
- `update_style()` forwards `(alpha, font_scale)` to the section like it does
  for bandwidth.
- The user's toggle is authoritative over availability: with the toggle off the
  section is hidden and its timer stopped, whatever the daemon is doing.

### R5 — Docs, version, tests

- `README.md`: new "AIO Monitoring" section (data source, thresholds, the
  read-only rationale, how to hide it), TOC entry, changelog entry.
- Version bump in `peripheral-battery.py` and `README.md`. **1.14.0**, approved
  by the user per the project finalization rules.
- Root `README.md` refreshed if the sub-project's description changed.
- Tests in `tests/test_aio_reader.py` (pure parsing, fixtures captured from the
  live API) and `tests/test_aio_section.py` (offscreen Qt render paths).

## Acceptance Criteria

- [x] AC1 — `aio_reader.build_snapshot()` parses the captured live fixture into
      `cpu_temp_c == 98.0`, `coolant_temp_c == 45.8`, `pump_rpm == 2399`, and
      four fan entries with their names and rpms.
- [x] AC2 — `build_snapshot()` gates `/api/devices/` on the presence of channels,
      not on `status == 1`; a response with `status: 0` and real devices yields
      `available: True`.
- [x] AC3 — The `"cluster"` pseudo-device (empty `GetDevice.devices`) is skipped
      and does not appear as a device or contribute fans.
- [x] AC4 — `"98.0 °C"`, `"208.4 °F"`, `"98"`, `""`, and `None` are each handled:
      the first two normalise to Celsius (208.4 °F → 98.0 °C), the third parses
      as 98.0, and the last two yield `None` without raising.
- [x] AC5 — With both API responses `None` (daemon unreachable),
      `build_snapshot()` returns `available: False` with a non-empty `error` and
      raises nothing.
- [x] AC6 — A devices response containing only non-AIO, non-fan channels yields
      `available: False` (nothing displayable), not an empty-but-available
      snapshot.
- [x] AC7 — A devices response with fan channels but no `AIO` channel yields
      `coolant_temp_c: None`, `pump_rpm: None`, and a populated `fans` list.
- [x] AC8 — Fan average excludes 0-rpm fans but the 0-rpm fan is still present in
      the `fans` list.
- [x] AC9 — `aio_reader.py --json` prints a valid JSON snapshot to stdout and
      exits 0 whether or not the daemon is reachable; logs go to stderr.
- [x] AC10 — `AioSection` constructed offscreen with a synthetic snapshot renders
      CPU, coolant, and fan text matching the snapshot values.
- [x] AC11 — Rendering a snapshot with `coolant_temp_c: None` hides the coolant
      row and the sparkline; the section remains visible for the other rows.
- [x] AC12 — Coolant colour banding: 44 °C → green, 52 °C → amber, 57 °C → red.
- [x] AC13 — After a snapshot with `available: False` and no prior success, the
      section is hidden and its poll interval is the slow (30 s) cadence.
- [x] AC14 — After a successful snapshot followed by a failing one, the section
      stays visible, keeps its last values, and marks the header
      `(unavailable)`; a subsequent success clears the marker.
- [x] AC15 — The sparkline retains at most 60 samples and drops the oldest.
- [x] AC16 — `aio_section_enabled: False` in settings hides the section on
      startup and the section's timer is stopped.
- [x] AC17 — The context menu contains an AIO submenu whose *Show AIO Section*
      item reflects and toggles `aio_section_enabled`, persisting to the config
      file.
- [x] AC18 — No fan, pump, RGB, or LCD **write** call exists anywhere in the new
      code (verified by grep for POST usage in `aio_reader.py` /
      `aio_section.py`).
- [x] AC19 — Full test suite passes on system python
      (`/usr/bin/python3 -m pytest tests/`).
- [x] AC20 — `README.md` documents the AIO section (source, thresholds,
      read-only rationale, hiding it), has a TOC entry, and carries a changelog
      entry for the approved version; the version string matches
      `peripheral-battery.py`.
- [x] AC21 — A live smoke run against the running daemon shows the section
      populated with plausible values, captured in the validation report.

## Risks & Assumptions

- **Assumption: localhost-only, unauthenticated API.** OpenLinkHub binds
  `127.0.0.1:27003` with no auth. The reader hardcodes that base URL (overridable
  via `OPENLINKHUB_API` for testing, matching `aio-color.sh`). Reaching a remote
  host is out of scope.
- **Risk: GUI stall on a hung daemon.** Mitigated by `QNetworkAccessManager` plus
  a 2 s transfer timeout — no blocking call on the GUI thread. This is the
  principal design constraint of R2.
- **Risk: API shape drift across OpenLinkHub releases.** The runbook already
  records one behaviour change between 0.8.8 and 0.9.1. Mitigated by treating
  every field as optional, keying on `description` rather than channel index, and
  degrading to hidden rather than crashing. The captured fixture pins today's
  shape so drift shows up as a test failure.
- **Risk: read-only scope eroding later.** Fan/pump writes are silently ignored
  by this firmware; adding controls would produce a UI that reports success and
  changes nothing. AC18 encodes the boundary.
- **Rollback**: revert the commit. The feature is additive — two new modules and
  one new default-`True` setting. Setting `aio_section_enabled: false` in
  `~/.config/peripheral-battery-monitor.json` disables it without a code change,
  and a stale key in an existing config file is ignored by older versions.
- **Assumption: 5 s poll cadence is cheap.** Two localhost GETs every 5 s against
  a daemon that is already polling the HID device continuously. No measurable
  cost expected; confirmed in the validation report.

## Alternatives Considered

- **`liquidctl status` subprocess** — rejected: a process spawn per poll, and the
  runbook documents liquidctl's read-verify guard failing outright on this device
  once OpenLinkHub has touched it.
- **sysfs `hwmon` / `lm_sensors`** — rejected: the Commander ST has no kernel
  driver (`corsair-cpro` covers only the older Commander PRO, `0x0c10`), so
  coolant and fan RPM are not exposed there at all.
- **`urllib` on the GUI thread** — rejected: up to 2×timeout of frozen UI when the
  daemon hangs.
- **`QThread` worker** — rejected: `QNetworkAccessManager` achieves the same
  without the worker/thread lifetime hazards that caused spec 010.
- **Graphing CPU temperature too** — rejected: at this widget size a spiky
  100 °C-boost trace reads as noise and obscures the slow coolant signal that
  actually predicts the alarm.
