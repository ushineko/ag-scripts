# Spec 001: Device Management

**Status: COMPLETE**

## Description
Core device listing and management for PulseAudio sinks and Bluetooth devices.

## Requirements
- Display PulseAudio sinks and Bluetooth devices in unified list
- Support drag-and-drop priority ordering
- Remember devices when disconnected (offline management)
- Use MAC addresses for stable Bluetooth identification

## Acceptance Criteria
- [x] Device list shows all sinks and Bluetooth devices
- [x] Drag-and-drop reordering works
- [x] Priority order persisted to config file
- [x] Offline devices retained in list
- [x] MAC-based identification for Bluetooth (AirPods, etc.)

## Implementation Notes
Core device management in `audio_source_switcher.py`. Config saved to `~/.config/audio-source-switcher/config.json`.
