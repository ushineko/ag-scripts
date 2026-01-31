# Spec 003: Desktop Entry

**Status: COMPLETE**

## Description
Create a desktop entry to add the launcher to the applications menu.

## Requirements
- Desktop entry file for "Alacritty Maximizer"
- Installation script copies to `~/.local/share/applications/`
- Uninstall removes the entry

## Acceptance Criteria
- [x] Desktop entry created with proper Exec path
- [x] `install.sh` installs to applications folder
- [x] Appears in system application launcher
- [x] `uninstall.sh` removes entry

## Implementation Notes
Desktop entry installed via `install.sh`.
