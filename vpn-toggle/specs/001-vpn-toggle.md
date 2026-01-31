# Spec 001: VPN Toggle Script

**Status: COMPLETE**

## Description
GUI-friendly script for managing NetworkManager VPN connections.

## Requirements
- Fuzzy connection name matching
- GUI menu via kdialog/zenity
- Enable/Disable/Bounce/Config actions
- Desktop notifications

## Acceptance Criteria
- [x] Fuzzy matches connection names (e.g., "vegas" matches full name)
- [x] GUI popup menu with kdialog/zenity
- [x] Enable action connects if disconnected
- [x] Disable action disconnects if connected
- [x] Bounce action restarts connection
- [x] Config opens network settings
- [x] Notifications via notify-send

## Implementation Notes
Created `toggle_vpn.sh`. Designed for keyboard shortcut binding.
