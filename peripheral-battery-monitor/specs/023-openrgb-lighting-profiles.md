# Spec 023: unified lighting profiles via OpenRGB

## Context

Specs 021 and 022 built RGB control on `liquidctl` and concluded this machine
had no controllable lighting, because liquidctl reports **zero colour channels**
for the NZXT Kraken 2024 Elite. That conclusion was wrong, and the error was
mine: liquidctl's lack of support is not the hardware's lack of capability.

**OpenRGB drives all of it**, including the Kraken:

| # | Device | Notes |
| --- | --- | --- |
| 0 | MSI GeForce RTX 4090 Suprim Liquid X | |
| 1 | Logitech G502 X PLUS | peripheral |
| 2 | **NZXT Kraken 2024 ELITE Series RGB** | the radiator fans' RGB daisy-chains into the Kraken |
| 3 | ASUS ROG MAXIMUS Z790 HERO | motherboard + ARGB headers |
| 4 | Corsair MM700 | peripheral |
| 5 | Keychron K4 HE | peripheral |

The user's fan lighting comes from device 2 — over the Kraken USB cable, the one
I had told them was not involved. Confirmed by setting it and observing the
change.

This spec moves lighting to OpenRGB and adds profiles that drive several devices
together. Cooling telemetry stays on liquidctl; the two are independent.

## Measured facts that drive the design

- **The OpenRGB CLI costs 9.1 s per invocation** because it re-detects every
  device. Against a running `openrgb --server` the same call takes **0.03 s**, a
  300x difference. A menu cannot use one-shot CLI calls.
- **Modes are per-device and do not overlap.** The GPU accepts
  `direct/breathing/flashing/off` and rejects `static`; the Kraken accepts
  `static`. A single broadcast command therefore fails on some devices — exactly
  how the GPU was silently switched off during investigation.
- **Device indices are not stable.** A server that has rescanned lists each
  device twice (12 entries for 6 devices), so indices must never be persisted.
  Devices are addressed by name.
- **OpenRGB and liquidctl coexist on the Kraken's HID.** Verified: telemetry
  reads correctly with the server running, and an RGB write lands in ~1 s while
  the monitor polls every 5 s. This was the main risk and it is not a problem.

## Requirements

1. Run OpenRGB as a managed systemd **user service**, started at login.
2. Talk to that server, never to the detecting CLI, from the UI.
3. Address devices by name; resolve names to current indices per operation.
4. Map a profile's intent onto each device's own supported mode, skipping
   devices that cannot express it rather than failing the whole profile.
5. Default profile scope is the **case interior**: Kraken, GPU, motherboard.
   Peripherals keep their own lighting.
6. Never block the GUI thread, and never disturb cooling telemetry.

## Acceptance Criteria

- [x] An `openrgb-server` systemd user unit exists, is stowed into dotfiles, and
      starts at login with a clean environment.
- [x] `rgb_openrgb.py` builds argv for listing devices and for setting a
      device's mode/colour through `--client`, never the detecting CLI form.
- [x] Device discovery parses the server's list into name/index pairs and
      tolerates the duplicate-index case by preferring the first match per name.
- [x] A profile resolves per device: an intent of "solid colour" maps to
      `static` where available and `direct` where not, and a device supporting
      neither is skipped with a log line, not an error.
- [x] Applying a profile issues one command per in-scope device, serialised, and
      reports which devices succeeded.
- [x] Default scope is Kraken + GPU + motherboard; peripherals are untouched.
- [x] Scope and last-applied profile persist in the existing settings file.
- [x] Every OpenRGB invocation runs through `QProcess`, off the GUI thread.
- [x] With the server down, lighting menus are disabled with a clear reason and
      nothing else in the widget is affected.
- [x] Cooling telemetry is unaffected while lighting commands run.
- [x] The liquidctl colour path (specs 021/022) is retired from the menu, since
      it cannot drive this hardware; the code is removed rather than left as a
      dead second backend.
- [x] Existing tests still pass.

## Risks & Assumptions

- **`--mode` silently accepting then misbehaving.** The GPU accepted a command
  whose mode it rejected and went dark. Profiles therefore validate the mode
  against the device's own list before sending, rather than sending and hoping.
- **An always-running OpenRGB server** is a new background process. It holds HID
  handles for six devices. Verified not to disturb liquidctl, but it is a new
  failure surface; the unit restarts on failure and the UI degrades if absent.
- **First detection costs ~9 s** at server start, so lighting is unavailable for
  a few seconds after login. Acceptable, and the UI reports it.
- **Peripherals are deliberately out of scope by default.** Mouse, keyboard and
  mousepad lighting is usually set deliberately and per-application; a profile
  that overrode it would be unwelcome.
- **Rollback**: revert the commit and stop/disable the unit. Lighting returns to
  whatever the devices were last set to; cooling is untouched throughout.

## Alternatives Considered

- Considered keeping liquidctl for the Kraken's colour; rejected because it has
  no colour channels for this model at all — the capability does not exist in
  that backend.
- Considered the `openrgb-python` SDK client; rejected to avoid adding a
  dependency when the shipped CLI in `--client` mode is already 0.03 s and fits
  the existing QProcess pattern.
- Considered driving lighting from the detecting CLI without a server; rejected
  at 9.1 s per click.

## Status: COMPLETE
