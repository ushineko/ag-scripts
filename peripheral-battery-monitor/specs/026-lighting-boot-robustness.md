# Spec 026: make lighting survive a reboot, and make its failures visible

## Context

After a reboot, lighting scenes stopped working — from the hotkeys *and* from the
context menu. Nothing reported an error. Diagnosis took far longer than it should
have, and the reasons why are themselves defects worth fixing.

Five distinct faults, found in this order:

### 1. `openrgb-server` starts before the hardware is enumerable

The unit added in spec 023 carries only `After=graphical-session.target`. On this
machine it started at 21:52:07, seconds into login, before USB/HID enumeration and
the uaccess ACLs were complete. **OpenRGB detects devices once, at startup**, so the
truncated list is frozen for the entire session:

```
0: MSI GeForce RTX 4090     1: Keychron K4 HE      (and duplicates)
```

The Kraken, the Aura motherboard, the MM700 and the G502 were all absent. Restarting
the same unit on a settled system finds all six immediately. Every downstream layer
then behaved correctly on an empty set and reported success.

This was never caught because spec 023 was verified by starting the server *by hand*
on an already-settled machine. The boot path — the only path that runs unattended —
was never exercised.

### 2. The monitor caches its own device list and never notices it is wrong

`_lighting_devices` is populated lazily and kept indefinitely. After the server was
fixed, the running monitor still held the empty list and still did nothing; it needed
its own restart. A monitor that has *zero* scoped devices while the server is up is in
a broken state and should say so.

### 3. stdlib log records lose their timestamp, level and logger name

`structlog.configure()` installs `TimeStamper`, `add_log_level` and
`add_logger_name`, but those apply only to structlog calls. Records from
`logging.getLogger(__name__)` — which is what every module outside
`peripheral-battery.py` uses — reach `ProcessorFormatter` with no
`foreign_pre_chain`, so they render as bare `{"event": "..."}`.

Consequence during this investigation: `scene_apply`, `lighting_write_failed` and
`lighting_devices_unknown` were all being logged correctly and were **impossible to
order in time or filter by level**. Several wrong conclusions were drawn from
"there are no log lines" when the lines existed but could not be correlated.

### 4. A scene reports success when it lit nothing

`apply_scene` ORs the colour and LCD halves. With an empty device list the colour half
applies to nothing, the LCD half succeeds, and `Apply` returns `true` over D-Bus. The
hotkey, the menu and the D-Bus API all reported success while no light changed.

### 5. Rapid scene changes overflow the queue and drop writes

Each scene issues one write per in-scope device (3) plus an LCD write. Three scenes
pressed in quick succession is 12 jobs against `MAX_PENDING = 8`, and the overflow
path drops jobs:

```
lighting_write_failed device=NZXT Kraken 2024 ELITE Series RGB err=dropped: queue full
lighting_write_failed device=ASUS ROG MAXIMUS Z790 HERO        err=dropped: queue full
aio_write_failed      what=lcd gif                              err=dropped: queue full
```

Dropping is the right instinct — an LCD GIF upload is slow and a backlog of stale
scenes is worthless — but it should drop *superseded* work, not arbitrary work, and
the user should end up in the state they last asked for.

## Requirements

1. The OpenRGB server must not start until its devices are enumerable.
2. A truncated or empty device list must be detected and surfaced, not absorbed.
3. Every log record must carry a timestamp, level and logger name.
4. A scene that changes nothing must not report success.
5. Rapid scene changes must converge on the last one requested, not drop at random.

## Acceptance Criteria

- [x] The `openrgb-server` unit waits for the cooler's HID device before starting, and
      the wait has a bounded timeout so a missing cooler cannot hang the unit forever.
- [x] Starting the unit on a freshly booted system yields the full device list — the
      same set a manual start on a settled system produces.
- [x] `AioSection` exposes a lighting health check that distinguishes: server down,
      server up but no devices, server up but no *scoped* devices, and healthy.
- [x] The monitor refreshes its device list on startup rather than only on first menu
      open, and re-refreshes when an apply finds no scoped devices.
- [x] Applying lighting with an empty device list logs a warning naming the cause and
      returns 0; it does not silently defer forever.
- [x] stdlib log records rendered to the file carry `timestamp`, `level` and `logger`,
      matching structlog-originated records.
- [x] `apply_scene` returns False when neither half changed anything, and the D-Bus
      `Apply` reflects that.
- [x] A scene's per-device lighting writes coalesce per device, so three scenes pressed
      in a second converge on the third rather than dropping work.
- [x] The LCD write of a scene coalesces with any pending LCD write.
- [x] Existing tests still pass.

## Risks & Assumptions

- **The HID wait is device-specific.** It keys on the Kraken because that is the device
  whose absence broke lighting here. A machine without it must still start the server,
  hence the bounded timeout: the wait is an optimisation for the common case, never a
  hard dependency.
- **Coalescing changes semantics.** Two rapid scenes will no longer both be applied;
  the later wins per device. That is the intent — lighting is a state, not a sequence —
  but it means a deliberate rapid A-then-B sequence shows only B.
- **Detection still happens once.** Even started at the right time, OpenRGB will not
  notice a device plugged in later. The health check makes that visible rather than
  fixing it; the remedy remains restarting the unit.
- **Rollback**: revert the commit and `systemctl --user restart openrgb-server` by hand
  after login. Cooling telemetry and pump alerting are untouched by all of this.

## Alternatives Considered

- Considered polling the OpenRGB server until the expected devices appear and
  restarting it if not; rejected as a loop that papers over startup ordering with
  retries, when the ordering itself is fixable.
- Considered raising `MAX_PENDING`; rejected because it delays the overflow rather than
  removing it, and a backlog of superseded scenes has no value even if it fits.
- Considered sending lighting writes outside the queue since they go to OpenRGB rather
  than liquidctl; rejected because the Kraken is reachable by both and serialisation is
  what keeps them from colliding.

## Status: COMPLETE
