# Spec 013: Generic Bluetooth Headphone Battery Support

**Status: COMPLETE**

## Description
Make the two bottom (headphone) cells of the monitor vendor-neutral. Instead of one cell pinned to SteelSeries Arctis (`headsetcontrol`) and the other pinned to Apple AirPods, both cells show whatever Bluetooth headphones are currently connected, prioritizing connected devices. Any headset that reports battery over BlueZ `org.bluez.Battery1` (e.g. the Sony WH-1000XM6) appears automatically, with no per-vendor code.

## Problem Statement
`get_all_batteries()` exposed two fixed keys — `headset` (SteelSeries via `headsetcontrol`) and `airpods` (Apple via D-Bus + BLE). A newly connected Sony WH-1000XM6 reports 59% cleanly via both UPower (`headset` type) and BlueZ `org.bluez.Battery1`, but had no slot in the UI because there was no Sony-specific reader. Adding a new reader per vendor does not scale.

## Requirements
- Add a vendor-neutral reader that enumerates **connected** Bluetooth audio devices via the BlueZ D-Bus `ObjectManager` and reads `org.bluez.Battery1` (`Percentage`). Audio devices are identified by `Icon` starting with `audio-` or by the presence of an audio service UUID. (Stable-contract rule: use D-Bus, not `bluetoothctl`.)
- Keep the AirPods BLE reader (L/R/case detail) and the SteelSeries `headsetcontrol` reader as **enrichment sources**, merged into the generic pool and de-duplicated by MAC.
- Rank the merged headphone list connected-first: devices with a known battery level rank ahead of connected-but-unknown devices.
- Emit the top two as `headphone1` / `headphone2`; the two bottom UI cells consume those keys.
- The UI cells display the real device name (existing `device_name` rendering); the fallback label when a cell is empty is "Headphones".
- Guard the "Connected / unknown-level" merge fallback so a cell whose occupant changes between polls cannot bleed the previous device's battery level onto a different device (match on `device_name`).

## Acceptance Criteria
- [x] `_enumerate_bt_audio_devices()` returns connected audio devices with their BlueZ `Battery1` level (None when no `Battery1`), keyed by MAC.
- [x] A connected Sony WH-1000XM6 (or any BlueZ `Battery1` headset) is surfaced by `get_headphones()` with its real name and level, with no vendor-specific code path.
- [x] AirPods present in both the generic pool and the BLE reader are de-duplicated by MAC; the richer (L/R/case) entry wins.
- [x] SteelSeries Arctis (USB dongle, not a BlueZ device) still appears via `headsetcontrol`.
- [x] Ranking is connected-first: a device with a known level ranks ahead of a connected device with unknown level.
- [x] `get_all_batteries()` emits `headphone1`/`headphone2`; the two bottom cells render them.
- [x] The merge fallback does not apply a cached level across a device-name change.
- [x] Tests pass.

## Implementation Notes
- `battery_reader.py`: add `_enumerate_bt_audio_devices()` and `get_headphones()`; `get_airpods_battery()` attaches `ids={'mac': ...}` so the dedup can match it; `get_all_batteries()` replaces the `headset`/`airpods` keys with `headphone1`/`headphone2`.
- `peripheral-battery.py`: rename the two bottom cells to `headphone1_ui`/`headphone2_ui` (fallback label "Headphones"); add the `device_name` guard in `update_single_device`'s merge block.

## Risks & Assumptions
- Rollback: revert the commit; the change is self-contained to `battery_reader.py` (new functions + `get_all_batteries` keys) and three small edits in `peripheral-battery.py`. No persisted state or schema change.
- Assumption: headsets that report battery expose it via `org.bluez.Battery1` (BlueZ experimental battery provider, standard on this stack — verified for the XM6). Headsets that report battery only via HFP/AVRCP without a `Battery1` provider would still need UPower fallback; out of scope here since UPower mirrors `Battery1` on this system.
- The BLE AirPods scan (~5s, only when AirPods are connected) is unchanged in cost; it now runs inside `get_headphones()`.
- Two-headphones-connected-at-once is rare; slot order between two simultaneously connected devices is by known-level then level then name (deterministic, documented).

## Alternatives Considered
- Generic-only (drop the AirPods/SteelSeries readers): rejected — loses AirPods L/R/case detail and Arctis USB-dongle support (the dongle is not a BlueZ device).
