# Spec 037: the mouse does not hold a host-set colour

> **Note**: This work has no associated issue tracker ticket. Consider creating one for traceability.

## Executive Summary

The mouse kept reverting to red instead of tracking the scene. OpenRGB sets a
volatile effect and the wireless G502 restores onboard state when it wakes, so
the colour was silently lost and nothing re-asserted it. A 60s timer re-sends the
current colour, scoped to that device alone.

## Context

Two wrong theories were eliminated first, both worth recording because each had
supporting evidence.

**Solaar conflict.** Plausible: solaar is used here for battery levels and had a
persisted `rgb_zone_1 = Static` left on the device. Disproved - no solaar daemon
runs on this machine, so nothing replays it.

**The device's idle timer.** `solaar show` reports `Idle Timeout: 1 Minute`, and
disabling it appeared not to take: the value stayed at 1 Minute after the write.
Both readings are worthless. `RGBIdleTimeout.read()` is
`return common.int2bytes(60, 2)  # default 1 minute` - a hardcoded constant, not
a device query, so it reports 1 Minute whatever the device holds. And its
`write()` calls a **host-side** `rgb_power` manager, so the idle effect only runs
while solaar does. With no daemon, the idle timer cannot be reverting anything.

What remains is the device itself: the G502 X PLUS is wireless, OpenRGB sets a
volatile effect, and onboard state is restored on wake. OpenRGB's CLI has no
device-persistence option (`--save-profile` is host-side), so the colour cannot
be made to stick. It has to be re-sent.

## Requirements

1. The mouse shows the current scene colour again after losing it.
2. Devices that do hold their colour are not written to repeatedly.
3. A re-assert is not recorded as a new user choice.
4. A downed OpenRGB does not produce a warning every minute.

## Acceptance Criteria

- [x] `reassert_lighting()` re-sends `_lighting_last_color` and returns the
      number of devices written.
- [x] It is scoped to `LIGHTING_REASSERT_SCOPE = ("g502",)`; a test with the
      mouse, Kraken and motherboard present asserts exactly one write.
- [x] It runs on its own timer at `LIGHTING_REASSERT_MS = 60_000`, independent of
      the cooler section's visibility.
- [x] `remember=False` - it neither persists settings nor emits
      `lightingChanged`; a test asserts no emission, and another asserts a real
      choice still emits.
- [x] No colour set yet, or an empty device list, is a silent no-op.
- [x] Verified live: with scene 3 (blue) active the mouse was forced to red
      behind the monitor's back, and the timer restored blue within 60s.
- [x] Existing tests still pass.

## Risks & Assumptions

- **The interval is a guess against an unmeasured sleep cycle.** 60s sits under
  the mouse's 5-minute sleep timeout with margin. The real wake behaviour was
  never observed directly - the fix was verified by simulating the revert.
- **The scope is hardcoded to this machine's mouse.** Another device with the
  same behaviour needs an entry; the cost of a wrong entry is one redundant
  write a minute.
- **This treats the symptom.** The colour cannot be persisted to the device
  through OpenRGB's CLI, so re-asserting is the available fix rather than the
  ideal one.
- **Rollback**: revert the commit. The mouse reverts on sleep again; nothing else
  changes.

## Alternatives Considered

- Considered persisting the colour to the device; rejected - OpenRGB's CLI
  exposes only host-side profiles.
- Considered re-asserting across the whole scope; rejected as a write per device
  per minute when only one device needs it.
- Considered re-asserting only on a detected wake event; rejected because no wake
  signal is available to the monitor without adding a HID++ listener, which is a
  great deal of machinery for a once-a-minute write.

## Status: COMPLETE
