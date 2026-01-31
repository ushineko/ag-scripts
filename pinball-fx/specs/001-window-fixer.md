# Spec 001: Window Fixer Utility

**Status: COMPLETE**

## Description
Force Pinball FX window to run on a specific monitor (e.g., portrait).

## Requirements
- Interactive menu for monitor selection
- Force window to selected monitor with resizing
- Persistent KWin rules

## Acceptance Criteria
- [x] Interactive menu shows available monitors
- [x] Forces window to selected monitor
- [x] Handles window resizing
- [x] Uses "Force" KWin rules
- [x] Persistent rules survive restarts

## Implementation Notes
Created `configure_kwin.py`. Designed to run after launching game via Heroic/Steam.
