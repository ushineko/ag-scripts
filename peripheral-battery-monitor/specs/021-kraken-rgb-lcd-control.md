# Spec 021: Kraken RGB and LCD control via liquidctl

## Context

Spec 019 added Colour, Effect and Brightness submenus for the AIO. They write to
the OpenLinkHub HTTP API, which addressed the Corsair Commander CORE's RGB
channels. That controller was replaced in September 2026 by an **NZXT Kraken
Elite V2** (`1e71:3012`), which OpenLinkHub does not manage. The snapshot now
reports `device_id: None` and `rgb_channels: []`, so the submenus never appear:
the feature is not degraded, it is gone.

Spec 020 moved cooler *reads* to `liquidctl`. This spec moves *writes* there
too, and adds the LCD, which the previous cooler did not usefully expose.

liquidctl's `KrakenZ3` driver gives this device:

| Capability | Call | Detail |
| --- | --- | --- |
| RGB | `set_color(channel, mode, colors)` | **not supported on this unit — see below** |
| LCD | `set_screen("lcd", mode, value)` | `liquid`, `brightness` 0-100, `orientation` 0/90/180/270, `static <path>`, `gif <path>` |

### Correction made during implementation: this device has no controllable RGB

The spec was drafted believing RGB was available, because
`_COLOR_CHANNELS_KRAKENX` lists `external`, `ring`, `logo` and `sync`. That is a
**class-level table shared across the Kraken family**, not a statement about any
particular unit. The driver assigns each instance its own `_color_channels`, and
for the NZXT Kraken 2024 Elite that map is **empty**:

```
$ liquidctl --match kraken set ring color fixed 0000ff
ERROR: NZXT Kraken 2024 Elite RGB: operation not supported by the device
```

All four channel names fail identically. Verified on the hardware, not inferred.
The "RGB" in the product name refers to the bundled RGB fans, which are driven
by a separate NZXT controller this machine does not have.

Consequences for this spec: the Colour and Effect requirements are implemented
but **gated behind a runtime capability probe** and therefore invisible on this
hardware. They are retained rather than deleted because the probe is cheap
(~0.09 s, no `connect()`), a different Kraken would light them up, and the
alternative — deleting working, tested code because today's device lacks a
feature — would have to be rewritten when the NZXT fans arrive. The LCD half of
the spec is fully functional and verified on the device.

The LCD is 640x640 (`lcd_resolution`). liquidctl resizes internally via Pillow
(12.3.0, present for system python), but rendering at native size avoids a
resample.

The user has asked for a **live rendered dashboard** on the LCD — coolant, CPU
temperature and pump speed, re-rendered and pushed periodically — rather than
only the firmware's built-in `liquid` readout. That choice is recorded here
along with its known cost, below.

## Requirements

1. Restore Colour and Effect control, writing through liquidctl instead of
   OpenLinkHub, preserving the existing `NAMED_COLORS` vocabulary.
2. Add LCD control: brightness, orientation, built-in `liquid` mode, a static
   image, and the live dashboard.
3. Render the dashboard with Qt, which is already a dependency. Do not add
   Pillow, matplotlib, or any image library to this project.
4. **Serialise every liquidctl invocation.** The status poll (spec 020) already
   runs `liquidctl status` every 5 s against the same hidraw node. RGB and LCD
   writes open that same node. Two concurrent invocations must never happen.
5. Never block the GUI thread; all liquidctl calls go through `QProcess`.
6. The dashboard is opt-in and its state persists in the existing settings file.
7. Survive the known LCD failure mode without user intervention.

## Known cost of the live dashboard, and how it is mitigated

Continuously updating this LCD provokes intermittent
`failed to switch active bucket` / `failed to setup bucket for data transfer`
errors that briefly blank the screen
([liquidctl#774](https://github.com/liquidctl/liquidctl/issues/774)), and
`set_screen` is marked *Unstable* upstream. This was raised before the choice
was made; the user opted for the dashboard, so the design absorbs the risk
rather than avoiding it:

- **Low cadence.** Default one push per 30 s, not per 5 s poll.
- **Change-gated.** Re-render only when a displayed value changes at displayed
  precision. A machine sitting at a steady idle pushes nothing at all.
- **Serialised.** A push never overlaps a status read or an RGB write.
- **Failure ceiling and surrender.** Retries stay on the same 30 s cadence
  rather than backing off further — the interval is already long — but
  consecutive failures are counted, and at the ceiling the dashboard disables
  itself, falls back to the firmware's `liquid` mode (which needs no host
  traffic and cannot blank) and notifies once. Cooling telemetry is never
  affected either way.

## Acceptance Criteria

- [x] `aio_liquid.py` builds liquidctl argv for: colour on a channel, an effect
      mode, LCD brightness, LCD orientation, LCD `liquid`, and LCD static image.
      Pure argv construction, no I/O, unit-tested.
- [x] Colour and mode validation rejects an unknown channel, an unknown mode, a
      malformed colour, brightness outside 0-100, and orientation not in
      {0,90,180,270}, without invoking anything.
- [x] `NAMED_COLORS` from `aio_color` is reused unchanged, so the menu's colour
      vocabulary is identical to spec 019.
- [x] Colour support is detected per device rather than assumed, and the Colour
      and Effect submenus are hidden entirely when the device implements no
      colour channel — as this one does not.
- [x] Effects are enumerated from the driver's own mode table, not hardcoded,
      and split into zero-colour modes and colour-taking modes.
- [x] A `LiquidctlQueue` serialises invocations: at most one QProcess in flight,
      writes ahead of reads, and a dashboard push dropped rather than queued when
      the queue is busy.
- [x] The spec 020 status poll runs through that queue, so no status read can
      overlap a write.
- [x] `render_dashboard()` produces a 640x640 QImage from a snapshot and is
      testable headless (offscreen platform), including with missing values.
- [x] The dashboard renders coolant temperature, CPU temperature and pump RPM,
      and degrades to placeholders for values the snapshot lacks.
- [x] A push occurs only when the rendered content differs from the last pushed
      content at displayed precision.
- [x] Consecutive push failures are counted; at the ceiling the dashboard
      disables itself, sets LCD `liquid` mode, and notifies once.
- [x] The context menu gains an LCD submenu (Brightness, Orientation, Liquid
      temperature, Live dashboard toggle, Static image...). Colour and Effect are
      implemented and appear only on a colour-capable device, which this is not.
- [x] The dashboard toggle persists across restarts via the existing settings
      file, defaulting to off.
- [x] With no Kraken present, every control is hidden and nothing is invoked.
- [x] `aio_color.py` (OpenLinkHub path) is retained and untouched for a future
      OpenLinkHub RGB device; the menu chooses a backend by which one reports a
      target.
- [x] Existing 280 tests still pass.

## Risks & Assumptions

- **`set_screen` is Unstable upstream.** A liquidctl release may change the
  interface. Mitigated by keeping argv construction in one module and by the
  fallback to `liquid` mode.
- **hidraw contention** is the main new risk, introduced by adding writes
  alongside the existing 5 s reads. The queue is the mitigation and is an
  acceptance criterion rather than an implementation detail.
- **RGB is unavailable on this unit**, confirmed by writing to every channel and
  by the empty instance `_color_channels`. The code path exists and is tested,
  but is dead on this hardware until a colour-capable device is attached. This
  was discovered during implementation and the spec was corrected rather than
  the finding being worked around.
- **A dashboard push is a visible hardware change** and is not readable back —
  the LCD's current content cannot be queried, so "restore what was there" is
  not possible. The toggle defaults to off for this reason.
- **Rollback**: revert the commit; the menu disappears and the LCD keeps
  whatever it was last set to. Cooling telemetry and alerting (spec 020) are
  untouched by this spec and continue working.

## Alternatives Considered

- Considered rendering with Pillow, which liquidctl already pulls in; rejected
  because Qt is already this project's toolkit and adding a second imaging
  stack to the app for one 640x640 canvas is not warranted.
- Considered pushing the dashboard every poll (5 s); rejected as needless
  hidraw traffic against a known-flaky path, with no benefit for values that
  move slowly.
- Considered dropping `aio_color.py`; rejected because it still correctly
  describes an OpenLinkHub RGB device and costs nothing to keep.

## Status: COMPLETE
