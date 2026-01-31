# Spec 001: Unified RGB Control

**Status: COMPLETE**

## Description
Single script to control RGB across OpenRGB, liquidctl, and ckb-next.

## Requirements
- Support OpenRGB (motherboard, GPU, RAM)
- Support liquidctl (Corsair AIO, Commander)
- Support ckb-next (Corsair peripherals)
- Basic color presets

## Acceptance Criteria
- [x] Controls all three RGB systems
- [x] Supports red, green, blue, white, off colors
- [x] OpenRGB for motherboard/GPU/RAM
- [x] liquidctl for Corsair cooling
- [x] ckb-next for Corsair peripherals

## Implementation Notes
Created `change_color.py`. Requires drivers for specific hardware.
