# Spec 014: Non-Headphone Bluetooth Device Battery Category

**Status: COMPLETE**

> **Note**: This work has no associated issue tracker ticket (personal public repo; per project policy no ticket is required).

## Description
Add a new, toggleable device category that surfaces the battery level of connected **non-audio** Bluetooth devices (e.g. input devices: a second BT mouse, a BT keyboard, a trackpad, gamepad, or stylus) that report `org.bluez.Battery1`. These are the mirror image of the existing headphone category, which covers only audio devices. The new category is selectable in either of the two top slots via the right-click → Devices menu, ranked connected-first (priority), exactly like the Headphone slots.

## Problem Statement
`get_all_batteries()` surfaces `mouse` (Logitech via `solaar`), `kb` (Keychron via UPower), and `headphone1`/`headphone2` (BlueZ **audio** devices via `org.bluez.Battery1`). Any *non-audio* Bluetooth device that reports a battery — a non-Logitech BT mouse, a second keyboard, a trackpad, gamepad, or stylus — has no slot and is invisible, even though BlueZ already exposes its `Battery1` percentage. Adding a fixed per-vendor reader does not scale; the audio path already solved this generically for headphones.

## Requirements
- Add a vendor-neutral reader that enumerates **connected** Bluetooth devices via the BlueZ D-Bus `ObjectManager`, keeps those that are **not** audio, and reads `org.bluez.Battery1` (`Percentage`). (Stable-contract rule: use D-Bus, not `bluetoothctl`.)
- Tighten the audio/headphone discriminator: a device is a headphone only when its BlueZ `Icon` starts with `audio-` (the Class-of-Device-derived signal), falling back to the audio-service-UUID sniff **only when the device exposes no `Icon` at all**. The prior "icon `audio-*` OR any audio UUID" test mis-filed non-headphone devices that merely advertise A2DP/audio profiles (e.g. an iPad, `Icon 'computer'`, which can source audio to the PC) as headphones. This is a behavioral change to the **headphone** category as well: such devices now fall into the non-headphone category instead of occupying a headphone slot.
- A non-audio device is only surfaced when it reports a battery level; connected-but-no-`Battery1` non-audio devices are omitted (there is nothing to show).
- Rank the resulting list connected-first, reusing the same priority key as headphones (known level first, then higher level, then name).
- Emit the top two as `btdev1` / `btdev2`.
- Add `btdev1` / `btdev2` as selectable slot categories (menu labels "Bluetooth Device" / "Bluetooth Device (2nd)", fallback label "Bluetooth"). Either of the two top slots can be set to them from right-click → Devices. Like headphones, these slots do **not** use the offline cache, so a disconnected device drops straight to the placeholder.
- Refactor the shared BlueZ walk so the audio and non-audio enumerators share one implementation (no copy-paste).

## Acceptance Criteria
- [x] `_enumerate_bt_devices(audio=False)` returns connected non-audio devices that expose `Battery1`, with their level; non-audio devices without `Battery1` are excluded.
- [x] `_enumerate_bt_devices(audio=True)` preserves the prior audio behaviour (audio devices, level `None` when no `Battery1`), and `_enumerate_bt_audio_devices()` still works for `get_headphones()` and its tests.
- [x] A connected BT mouse/keyboard reporting `Battery1` (e.g. `{'mac','name','level':72}`) is surfaced by `get_bt_devices()` with its real name and level, no vendor-specific code path.
- [x] An audio device (headphone, `Icon 'audio-*'`) is NOT surfaced by `get_bt_devices()` (it belongs to the headphone category).
- [x] A device advertising audio/A2DP UUIDs but with a non-audio `Icon` (e.g. an iPad, `Icon 'computer'`) is classified non-audio: it is surfaced by `get_bt_devices()`, not by `get_headphones()`.
- [x] Fallback preserved: a device with a blank `Icon` but an audio UUID is still treated as a headphone.
- [x] Ranking is connected-first: a device with a higher known level ranks ahead of a lower one; order is deterministic.
- [x] `get_all_batteries()` emits `btdev1`/`btdev2` from the top two non-audio battery devices.
- [x] `btdev1`/`btdev2` are valid slot categories: `_valid_slot` accepts them, the Devices menu lists them, and a slot set to `btdev1` resolves `results['btdev1']` in `on_data_ready` with `use_offline_cache=False`.
- [x] Tests pass.

## Implementation Notes
- `battery_reader.py`: extract `_enumerate_bt_devices(audio: bool)` from the existing `_enumerate_bt_audio_devices()`; keep `_enumerate_bt_audio_devices()` as a thin `audio=True` wrapper. Add `get_bt_devices()` (non-audio, ranked). Generalize `_headphone_rank_key` → `_bt_rank_key` (used by both `get_headphones` and `get_bt_devices`). `get_all_batteries()` gains `btdev1`/`btdev2`.
- `peripheral-battery.py`: add two `SLOT_TYPES` rows for `btdev1`/`btdev2` (cache `False`). The slot machinery (menu build, `_assign_slot`, `_set_slot`, `on_data_ready` routing) is already generic over `SLOT_SPECS`, so no other UI changes are required.

## Risks & Assumptions
- Rollback: revert the commit; the change is self-contained to `battery_reader.py` (new/refactored functions + two `get_all_batteries` keys) and two added `SLOT_TYPES` rows in `peripheral-battery.py`. No persisted state or config schema change; unknown slot values already fall back to defaults via `_valid_slot`.
- Assumption: non-audio devices that have a battery expose it via `org.bluez.Battery1` on this stack (same provider the headphone path relies on).
- Overlap: a device already shown by the `mouse` (Logitech/solaar) or `kb` (Keychron/UPower) slot may also appear under `btdev*` if it reports `Battery1`. This is acceptable — slots are user-chosen — and mirrors the AirPods overlap the headphone path already tolerates.
- Behavioral change to the headphone category: the tightened `Icon`-primary discriminator means a device that only advertises audio UUIDs but is not an `audio-*` peripheral (iPad/phone/computer) no longer appears in a headphone slot. Verified against a live iPad (`Icon 'computer'`, A2DP UUID, `Battery1` 80%): before, it was surfaced as `headphone1`; after, as `btdev1`. A headphone with a blank icon (unusual) still resolves via the UUID fallback.
- Scope: category includes any non-audio BlueZ `Battery1` device (per design decision), so a phone/watch reporting battery could appear; that is intended and rare.

## Alternatives Considered
- Restrict to HID input devices only (Icon `input-*` / HID UUID): rejected per design decision — the request is "non-headphone Bluetooth devices"; the broadest non-audio filter is simpler (exact inverse of the audio enumerator) and needs no HID allow-list.
- A separate dedicated collapsible section listing all such devices: rejected per design decision — the two-slot selectable-category model is consistent with headphones and needs no window-layout changes.
