# Spec 007: Keychron Bluetooth Battery Priority

**Status: COMPLETE**

## Description
When a Keychron keyboard is plugged in via USB for charging but still connected via Bluetooth, prioritize showing the Bluetooth battery level (if available) rather than showing "Wired" status with no battery readout.

## Problem Statement
Currently, `get_keyboard_battery()` checks for USB connection first. When the keyboard is plugged in for charging, it returns "Wired" with level=-1, even though the keyboard is still operating on Bluetooth and has battery info available via UPower.

## Requirements
- Check UPower for Bluetooth battery **before** checking USB wired connection
- Only show "Wired" status if no Bluetooth battery is available via UPower
- Maintain fallback to 2.4G wireless detection as the last resort

## Acceptance Criteria
- [x] UPower Bluetooth battery check runs before USB wired check
- [x] When keyboard is charging via USB but connected via Bluetooth, battery % is displayed
- [x] When keyboard is wired-only (no Bluetooth), "Wired" status is still shown
- [x] 2.4G wireless fallback still works when neither BT nor USB is detected
- [x] Tests pass

## Implementation Notes
Modify `get_keyboard_battery()` in `battery_reader.py` to reorder the detection logic.
