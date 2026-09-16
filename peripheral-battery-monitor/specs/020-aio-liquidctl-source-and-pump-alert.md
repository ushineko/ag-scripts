# Spec 020: liquidctl AIO source and pump-failure alert

## Context

The AIO section (spec 017) reads liquid-cooler thermals exclusively from the
OpenLinkHub HTTP API. That was correct while the cooler was a Corsair H150i
ELITE driven by a Commander CORE. In September 2026 the Corsair pump failed
with no warning, the CPU reached 100 C and hard-throttled to 0.20 GHz, and the
whole cooling assembly — Commander CORE, pump, radiator and fans — was replaced
with an **NZXT Kraken Elite V2** (`1e71:3012`).

Two consequences:

1. **OpenLinkHub no longer manages a cooler.** It still manages the MM700
   mousepad and the HX1000i PSU, so the daemon answers normally, but no channel
   reports coolant or pump data.
2. **The kernel has no driver for this cooler.** `nzxt-kraken3` matches
   `2007/2014/3008/300C/300E`; `3012` is absent, so no hwmon node exists and
   `sensors` reports nothing. `liquidctl` 1.16.0 does support it, as
   "NZXT Kraken 2024 Elite RGB".

The reader currently degrades in the worst possible direction. Its cooler
fallback accepts any channel advertising a temperature, and the HX1000i exposes
`description: "Probe"` channels named "VRM Temperature" and "PSU Temperature".
A live snapshot on the repaired machine returns:

```json
{"available": true, "coolant_temp_c": 43.5, "coolant_label": "VRM Temperature",
 "pump_rpm": 0, "fans": []}
```

That is a PSU VRM sensor presented as coolant, beside a pump reading of exactly
`0` — indistinguishable from a stopped pump. The section renders, and looks
plausible. This is the same class of blind spot that let the original pump death
go unnoticed: the widget was incapable of reporting the failure it most needed
to report.

## Requirements

1. Read cooler thermals from `liquidctl --json status` as the preferred source.
2. Keep OpenLinkHub as a fallback cooler source, so a future Corsair cooler or a
   broken liquidctl still yields a reading.
3. Never present a non-cooler sensor as coolant.
4. Distinguish "pump speed not reported" from "pump reporting zero rpm".
5. Raise a desktop alert when the pump stops or the coolant runs hot, debounced
   so a single bad sample cannot spam, and cleared on recovery.
6. Do not block the GUI thread. `aio_section.py` uses `QNetworkAccessManager`
   specifically to avoid blocking; a subprocess must be driven the same way.
7. Degrade cleanly at every level: no liquidctl binary, liquidctl present with
   no cooler, OpenLinkHub down, both down.

## Acceptance Criteria

- [x] `aio_reader.parse_liquidctl()` turns `liquidctl --json status` output into
      coolant temperature, pump rpm and fan list; returns None for unusable input.
- [x] `build_snapshot()` accepts a third `liquid_json` argument and prefers it
      over OpenLinkHub for coolant, pump and cooler fans.
- [x] A snapshot built from OpenLinkHub data containing only HX1000i "Probe"
      channels reports `coolant_temp_c: None` and `pump_rpm: None` — not the VRM
      temperature and not `0`.
- [x] A cooler channel whose description is a genuine cooler role ("AIO",
      "Pump", "Water Block", "Liquid") is still accepted from OpenLinkHub.
- [x] `pump_rpm` is `None` when unreported and an int when reported, so `0` means
      a pump that genuinely reads zero.
- [x] `evaluate_alert()` is pure and returns a state of `ok`, `warning` or
      `critical` with a reason; pump rpm 0 and coolant above the critical ceiling
      both yield `critical`.
- [x] The alert requires consecutive confirming samples before firing, re-notifies
      no more often than the re-alert interval, and emits a recovery notification
      once the condition clears.
- [x] `aio_section.py` runs liquidctl via `QProcess` (not `subprocess`) so the
      GUI thread never blocks, and skips a poll while one is already in flight.
- [x] With liquidctl absent, the snapshot still builds from OpenLinkHub and sets
      no alert state from missing data.
- [x] With both sources unavailable, `available` is False and `error` is set.
- [x] Missing pump data never raises an alert — absence of evidence is not a
      stopped pump.
- [x] `aio_reader.py --json` prints a snapshot including the liquidctl source on
      the live machine.
- [x] Existing 98 tests still pass.

## Risks & Assumptions

- **liquidctl needs HID access.** It reads `/dev/hidraw*`; the logged-in user
  gets this via the uaccess ACL. If that fails the reader degrades to OpenHub
  rather than erroring. Historical note: `logid`, `solaar` and `battery_reader`
  contending on one hidraw node produced 25 s timeouts on this machine, so the
  subprocess carries a short timeout and the section never queues polls.
- **liquidctl latency** measured at 0.15-0.16 s on this hardware. Acceptable for
  an out-of-process async call, unacceptable as a blocking GUI-thread call at a
  5 s poll interval — hence QProcess.
- **Thresholds are judgement, not vendor spec.** Coolant warn 50 C / critical
  60 C, pump warn below 500 rpm / critical at 0. Idle observed: coolant 36.3 C,
  pump 1725 rpm at 35% duty. Tunable by constant.
- **Rollback**: revert the commit. The section degrades to its previous
  behaviour, which is cosmetically wrong but not harmful.
- **Not addressed here**: the case rear fan is currently disconnected pending
  replacement NZXT fans, and no motherboard fan RPM is readable at all
  (`asus_ec_sensors` has no MAXIMUS Z790 HERO alias). Only cooler fans reported
  by the Kraken appear in the snapshot.

## Alternatives Considered

- Considered using the `nzxt-kraken3` kernel driver; rejected because it does
  not match `3012` and patching a kernel module is far out of proportion.
- Considered polling liquidctl from a standalone systemd timer; rejected because
  the user asked for it inside the existing monitor, and a second poller would
  contend for the same hidraw node.
- Considered dropping the OpenLinkHub cooler path entirely; rejected to keep a
  fallback source if liquidctl or HID access breaks.

## Status: COMPLETE
