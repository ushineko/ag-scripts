# Spec 032: ASUS ARGB headers need Direct, not Static

> **Note**: This work has no associated issue tracker ticket. Consider creating one for traceability.

## Executive Summary

Scenes left a new ARGB-header fan dark while reaching every other device. Two
causes: the header had zero LEDs configured in OpenRGB (configuration, fixed by
`--size`), and `resolve_mode` sent `Static`, which on the ASUS Aura controller
drives only the onboard LED. Solid-colour mode preference is now per-device, so
the board gets `Direct` while the GPU keeps `Static`. Reviewers should look at
`SOLID_MODE_OVERRIDES` in `rgb_openrgb.py` and at the regression test naming the
GPU case.

## Context

An NZXT dual-frame fan was wired to a motherboard ARGB header. Scenes reached
every other device and left the fan dark.

Two independent faults, found in order:

1. **The header had zero LEDs configured.** OpenRGB cannot detect the length of
   an ARGB strip — nothing on the header reports back — so it defaults each
   addressable zone to 0 and writes to a zone of length zero. Fixed outside the
   code by `--zone N --size 16`, which OpenRGB persists in
   `~/.config/OpenRGB/Configuration.json`. No code change; recorded here because
   the symptom is identical to a software fault.
2. **`Static` does not drive the addressable headers.** This is the code fault.

`resolve_mode` prefers `static` for a solid colour:

```python
SOLID_MODES = ("static", "direct")
```

The ASUS Aura mainboard device advertises both `Static` and `Direct`, so the
monitor picks `Static`. On this controller `Static` drives only the onboard LED;
the four `Addressable RGB Header` zones go dark. `Direct` drives them.

Confirmed by A/B on one device with one colour: `--mode static --color 0000FF`
turned the fan off, `--mode direct --color 0000FF` lit it blue.

**`static`-first is not a mistake to be reversed.** The comment in `resolve_mode`
records why it exists: the RTX 4090 rejects `static`, and an earlier attempt to
send it turned the GPU's lighting off. The preference is protecting that device.
So the order has to become per-device rather than global.

## Requirements

1. A device whose addressable zones only render in `Direct` receives `Direct` for
   a solid colour.
2. Devices that need `static` first keep it. The GPU behaviour that motivated the
   original order must not regress.
3. A device advertising only one of the two is unaffected.
4. The override is by device name, consistent with how lighting scope already
   addresses devices, because OpenRGB indices are unstable.

## Acceptance Criteria

- [x] `resolve_mode` accepts the device name and returns `Direct` for the ASUS
      Aura mainboard device when the intent is `solid`, even though the device
      also advertises `Static`.
- [x] For a device not in the override list, `resolve_mode` still prefers
      `static`, with an explicit test naming the GPU case.
- [x] A device advertising only `Static` still gets `Static`; a device advertising
      only `Direct` still gets `Direct`; a device advertising neither still
      returns `None`.
- [x] The override matches case-insensitively on a substring of the device name,
      and is data, not branching logic.
- [x] The `off` intent is unchanged for every device.
- [x] The call site in `aio_section` passes the device name.
- [x] Existing tests still pass.

## Risks & Assumptions

- **The override is name-based and therefore a heuristic.** It is the same
  heuristic the lighting scope already relies on, and OpenRGB indices are
  unstable, so a name match is the available option.
- **`Direct` on the Aura device is assumed not to regress the onboard LED.**
  Observed lighting correctly under `Direct` during the A/B.
- **Zone sizes are configuration, not code.** A fresh OpenRGB profile, or a reset
  of `Configuration.json`, returns the headers to 0 LEDs and the fan goes dark
  again with no code fault. This is recorded in the runbook.
- **Rollback**: revert the commit. The motherboard returns to `Static` and the
  ARGB headers stop responding to scenes; nothing else changes.

## Alternatives Considered

- Considered reversing `SOLID_MODES` globally to `("direct", "static")`; rejected
  because `static`-first exists to protect the RTX 4090, which rejects `static`
  — the failure that motivated the current order.
- Considered choosing the mode from whether the device reports addressable zones
  rather than from its name; rejected for now because the call site has only the
  name and mode list, and fetching per-device zone data would add a round trip to
  every scene apply. Worth revisiting if the override list grows.

## Status: COMPLETE
