# Spec 003: Microphone Association

**Status: COMPLETE**

## Description
Link microphones to output devices for automatic input switching.

## Requirements
- Auto mode: Intelligently match Bluetooth/USB device pairs
- Manual mode: Link specific mic to specific output via context menu
- Switch input when output changes

## Acceptance Criteria
- [x] Auto mode matches device pairs (e.g., AirPods output -> AirPods mic)
- [x] Context menu "Link Microphone" option available
- [x] Input switches automatically with output
- [x] Bluetooth mic names display correctly

## Implementation Notes
Added in v11.5. Context menu for manual linking, smart matching for auto mode.
