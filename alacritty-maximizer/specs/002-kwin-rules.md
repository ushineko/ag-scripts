# Spec 002: KWin Rules Installation

**Status: COMPLETE**

## Description
Create scripts to inject KWin rules for maximized, borderless Alacritty windows on specific monitors.

## Requirements
- Install KWin rules matching the special window class
- Apply position, maximized state, and no decorations
- Reload KWin after installation
- Provide uninstall capability

## Acceptance Criteria
- [x] `install_kwin_rules.py` creates rules in `~/.config/kwinrulesrc`
- [x] Rules force window to monitor coordinates
- [x] Rules apply maximized state and remove titlebar
- [x] KWin reloads rules after installation
- [x] `uninstall.sh` removes rules and desktop entry

## Implementation Notes
Created `install_kwin_rules.py` and shell scripts for installation/uninstallation.
