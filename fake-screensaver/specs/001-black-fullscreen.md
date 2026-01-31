# Spec 001: Black Fullscreen Window

**Status: COMPLETE**

## Description
PyQt application that displays a black fullscreen window with visible cursor.

## Requirements
- Cover entire screen with black
- Keep mouse cursor visible (unlike real screensavers)
- Easy exit via Esc key

## Acceptance Criteria
- [x] Fullscreen black window covers monitor
- [x] Mouse cursor remains visible
- [x] Esc key closes window
- [x] Desktop entry for application launcher

## Implementation Notes
Created `fake_screensaver.py` with PyQt6. Useful for VM/remote scenarios.
