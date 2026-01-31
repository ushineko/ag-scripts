# Spec 001: Monitor Selection GUI

**Status: COMPLETE**

## Description
Create a PyQt6 GUI that allows users to select which monitor to launch Alacritty on, or launch normally.

## Requirements
- Display available monitors with their positions
- Allow selection of specific monitor or "Normal Start"
- Launch Alacritty with appropriate window class for KWin rules

## Acceptance Criteria
- [x] PyQt6 GUI displays monitor list
- [x] "Normal Start" option available
- [x] Monitor selection triggers Alacritty with special class `--class alacritty-pos-X_Y`
- [x] Uses screen coordinates for robust monitor identification

## Implementation Notes
Created `main.py` with PyQt6 GUI. v1.1 switched to screen coordinates for robustness.
