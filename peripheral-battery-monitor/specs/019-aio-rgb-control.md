# Spec 019: On-Demand AIO RGB Control

> **Note**: This work has no associated issue tracker ticket. This is a personal
> public repository with no issue tracker (see `.claude/CLAUDE.md`).

## Status: COMPLETE

## Executive Summary

Brings `sysadmin/scripts/aio-color.sh` into the widget: right-click → **AIO** now
has Colour, Effect, and Brightness submenus. This is the first time the monitor
writes to hardware, which narrows spec 017's read-only rule rather than breaking
it — RGB writes land, fan and pump duty writes are silently discarded by this
firmware, and 019 AC12 keeps the guard against speed endpoints.

Review the staged execution in `aio_section._run_stages` first: the override must
land before the profile select, and the reverse order is a silent no-op on the
hardware, so ordering is enforced by the dispatcher and asserted by test. Two
places improve on the shell script — RGB channels come from the `rgbDevices` map
already in the poll response instead of a 16-channel probe, and effect names come
from the per-device `GET /api/color/` instead of the global `rgb.json`, which
lists effects this cooler does not implement.

## Context

`~/git/sysadmin/scripts/aio-color.sh` sets a solid colour or an RGB effect on
OpenLinkHub-managed Corsair devices. This spec brings that capability into the
monitor's right-click menu so colours can be changed without dropping to a
shell.

### This amends spec 017's read-only rule

Spec 017 made the AIO section read-only, and AC18 asserts that no write call
exists in `aio_reader.py` or `aio_section.py`. That rule was about **fan and pump
duty**, which Commander ST firmware 2.x silently discards: a speed control would
report success and change nothing. The runbook is equally explicit that **RGB and
LCD control do work**.

The boundary therefore moves from "no writes" to "no *speed* writes". 017 AC18 is
superseded by AC12 below, which keeps the original guard against
`/api/speed`, `/api/psu/speed`, and the `/api/temperatures/` fan-curve endpoints
while permitting RGB writes. Spec 017 stays COMPLETE and tagged; the amendment
lives here.

### Traps this must encode

All four are documented in
`~/git/sysadmin/runbooks/aio-coolant-overtemp-and-commander-st-fan-control.md`
and all four produce silent failure, not an error:

1. **Colour lives in `RGBOverride`, not `rgb.json`.** Editing the `static`
   profile applies cleanly, survives a restart, and changes no LED. The working
   sequence is: set the per-channel override (enabled, start and end colour),
   *then* select the `static` profile.
2. **An effect needs the override disabled first**, or the override masks the
   animation.
3. **`Brightness: 0` blacks everything out.** Colour commands then succeed and
   nothing lights up.
4. **Profile names cannot be invented.** They map to effect implementations in
   Go; an unknown name returns `"Unable to change device RGB profile"`.

### Two places this improves on the shell script

Both were found by reading the API rather than porting the script as-is:

- **Channel discovery.** The script probes channels 0–15 with `getOverride` and
  filters on a populated `RGBStartColor`, because `getOverride` returns
  `status:1` for channels that do not exist. Unnecessary: `/api/devices/` already
  carries an `rgbDevices` map, which lists exactly channels 0–6 on this cooler,
  matching what the probe finds. The monitor already fetches that endpoint every
  poll, so discovery costs nothing and needs no extra requests.
- **Effect list.** The script reads `/var/lib/openlinkhub/database/rgb.json` off
  disk and offers every profile in it. That file is global, so the script offers
  the cooler effects it does not support (`keyboard`, `mouse`, `headset`, `tlk`,
  `stand`, ...). `GET /api/color/` returns profiles **per device**: 28 for this
  cooler against the file's 40-odd. Using the API is both correct and consistent
  with the project's preference for stable programmatic contracts over
  filesystem paths.

## Requirements

### R1 — Reader: expose the RGB target

`aio_reader.build_snapshot()` gains three fields describing what RGB writes would
address, sourced from the `/api/devices/` response already being fetched:

```python
"device_id": str | None,        # serial of the cooler-bearing device
"rgb_channels": [int, ...],     # from rgbDevices, numerically sorted
"brightness": int | None,       # DeviceProfile.Brightness, 0-3
```

The device chosen is the one owning the AIO channel, matching how the script
picks its default device. When no device has an AIO channel, the first device
with RGB channels is used, so a non-cooler RGB device is still addressable.

### R2 — New module: `aio_color.py`

Pure request builders plus a synchronous applier, mirroring the
`aio_reader` split. No Qt imports.

- `NAMED_COLORS`: the script's 13 names, values identical to it.
- `parse_color(value) -> (r, g, b) | None`: a name or `#rrggbb`.
- `solid_requests(device_id, channels, rgb, *, brightness=None)` and
  `effect_requests(device_id, channels, profile, *, brightness=None)` return an
  ordered list of **stages**, each stage a list of `(path, payload)` pairs.
  Stages are ordered because the override must land before the profile select;
  requests within a stage are independent.
- `brightness_request(device_id, level)`.
- When `brightness` is passed as `0`, a brightness-repair request is prepended.
  A user picking a colour wants a visible colour, and trap 3 would otherwise make
  the command look broken. Any other level is left alone.
- CLI: `aio_color.py <colour|#hex|effect>`, `--list`, `--brightness N`, for
  debugging without the GUI.

### R3 — Section: execute the stages

`AioSection` gains `apply_color`, `apply_effect`, and `set_brightness`, posting
over the existing `QNetworkAccessManager`. A stage is dispatched only once every
request in the previous stage has finished, which is what preserves the
override-then-profile ordering. Failures are logged and abandoned; no retry, no
dialog.

The section caches the per-device effect list from `GET /api/color/`, fetched
once after the first successful snapshot. When that fetch has not succeeded, the
effect list is empty and the menu omits effects rather than guessing names
(trap 4).

### R4 — Menu

Under the existing **AIO** submenu, shown only when RGB channels are known:

```
AIO ▸ Show AIO Section          [x]
      ─────
      Colour ▸      red … teal, Custom…, Off
      Effect ▸      <the device's own profiles>
      Brightness ▸  33% · 66% · 100%
```

`Custom…` takes a `#rrggbb` value through `QInputDialog`, following the existing
*Add Interface…* pattern. `Off` is a solid black, matching the script.
`static` and `off` are filtered out of the effect list, since both are reachable
through the Colour menu.

### R5 — Docs, version, tests

README section covering the menu, the sequence, the brightness trap, and the
speed-vs-RGB boundary. Version bump, changelog, tests.

## Acceptance Criteria

- [x] AC1 — `build_snapshot()` on the live fixture returns
      `device_id == "207132833748"`, `rgb_channels == [0,1,2,3,4,5,6]`, and
      `brightness == 3`.
- [x] AC2 — With two devices where only the second owns an AIO channel,
      `device_id` is the second. With no AIO channel anywhere, it is the first
      device having RGB channels. With no RGB channels at all, it is `None` and
      `rgb_channels` is empty.
- [x] AC3 — `parse_color` resolves every name in `NAMED_COLORS`, resolves
      `#ff8800` to `(255, 136, 0)`, is case-insensitive, and returns `None` for
      `"nope"`, `"#12345"`, and `""`.
- [x] AC4 — `solid_requests` emits two stages: every channel's
      `color/setOverride` with `enabled: true` and equal start/end colour, then
      every channel's `color` with `profile: "static"`. Ordering is asserted,
      because reversing it is the documented silent failure.
- [x] AC5 — `effect_requests` emits `color/setOverride` with `enabled: false`
      before selecting the named profile.
- [x] AC6 — Passing `brightness=0` prepends a `brightness` request with level 3
      as its own first stage; passing 1, 2, 3, or `None` prepends nothing.
- [x] AC7 — `brightness_request` rejects a level outside 0–3.
- [x] AC8 — `AioSection.apply_color` dispatches stage 2 only after every stage-1
      reply has finished, verified with a fake network layer that records
      dispatch order.
- [x] AC9 — A failed request in stage 1 does not prevent stage 2, does not
      raise, and does not stop the poll timer.
- [x] AC10 — The effect list is empty until the profiles fetch succeeds, and is
      populated from `GET /api/color/` for the section's own device only.
      `static` and `off` are excluded.
- [x] AC11 — The context menu shows Colour, Effect, and Brightness submenus when
      RGB channels are known, and omits all three when they are not. Selecting a
      colour calls `apply_color` with the right RGB triple.
- [x] AC12 — **Supersedes 017 AC18.** No speed-write path exists in any AIO
      module: `/api/speed`, `/api/psu/speed`, `/api/temperatures/new`,
      `/api/temperatures/update`, `/api/temperatures/updateGraph`, and
      `setSpeed` appear nowhere. RGB writes are permitted.
- [x] AC13 — Full test suite passes on system python.
- [x] AC14 — README documents the menu, the override-then-profile sequence, the
      brightness trap, and why speed control is absent while colour control is
      present. Version matches between source and README; changelog entry
      present.
- [x] AC15 — Live verification against the daemon: a colour applied from the
      section is readable back through `getOverride` on every channel, and the
      pre-existing colour is restored afterwards. Captured in the validation
      report.

## Risks & Assumptions

- **Risk: writing to hardware from a passive monitor.** The widget was
  read-only until now. Mitigated by scope: RGB only, one device, user-initiated
  from a menu, no automatic or scheduled writes, and AC12 keeping speed
  endpoints out by test.
- **Risk: the brightness repair surprises someone.** Raising brightness is only
  triggered at level 0, where every LED is already dark and a colour request
  cannot otherwise be satisfied. Levels 1–3 are never touched.
- **Risk: colour state is persistent.** Unlike every other write in this
  project, this one outlives the process — OpenLinkHub stores the override in
  the device profile. Testing must capture and restore the existing colour.
- **Assumption: `static` exists on any RGB-capable device.** True for both
  devices this daemon reports. A device without it would fail the profile select
  and log; the override write would still have landed.
- **Assumption: unauthenticated localhost API.** Unchanged from 017. Any process
  on this machine could already do this; the monitor adds no new exposure.
- **Rollback**: revert the commit. No config key and no persisted app state. RGB
  state already written to the device is unaffected by a rollback and is changed
  back with the script or the WebUI.

## Alternatives Considered

- **Shelling out to `aio-color.sh`.** Rejected: a subprocess per colour change,
  a hard dependency on a path in another repo, and it carries the two
  weaknesses this spec's R2 notes fix.
- **Porting the script's 16-channel probe.** Rejected: `rgbDevices` in a
  response already being fetched gives the same answer for free.
- **Reading effect names from `rgb.json`.** Rejected: the file is global, so it
  offers effects the target device does not implement, which trap 4 turns into
  an error dialog's worth of failures.
- **A colour picker dialog.** Rejected for now: `QColorDialog` is a heavy modal
  for a frameless always-on-top widget. `Custom…` with a hex field covers it.
