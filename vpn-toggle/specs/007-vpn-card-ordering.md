# Spec 007: VPN Card Ordering

**Status**: INCOMPLETE

## Overview

Allow the user to reorder VPN connection cards in the GUI and persist that order across restarts. Newly discovered VPNs append to the end.

## Motivation

With multiple VPN backends, the card list can grow. The user should be able to put their most-used VPNs at the top. Currently the order is determined by backend discovery order (NM VPNs first, then OpenVPN3), which is arbitrary.

## Design Decisions

### Up/Down Buttons vs Drag-and-Drop

Use up/down arrow buttons on each card rather than drag-and-drop.

**Rationale**: Drag-and-drop on `QScrollArea` with `QFrame` children requires custom `QMimeData` handling and is fragile on Wayland. Arrow buttons are simple, accessible, and match the existing button-row pattern on each card. With only a handful of VPNs, arrow buttons are perfectly adequate.

### Persistence

Store the order as a `"vpn_order"` list (of VPN names) in `config.json` at the top level. The GUI sorts discovered VPNs by this list on startup. VPNs not in the list (newly discovered) are appended at the end.

## Requirements

- [ ] Add up/down arrow buttons to each VPN card (right side of the button row)
- [ ] Clicking up moves the card one position up; clicking down moves it one position down
- [ ] First card's up button and last card's down button are disabled
- [ ] Order is saved to `config.json` as `"vpn_order": ["vpn1", "vpn2", ...]` on every reorder
- [ ] On startup, `populate_vpn_list()` sorts discovered VPNs by the saved order
- [ ] Newly discovered VPNs (not in the saved order) appear at the end
- [ ] VPNs in the saved order but no longer discovered (removed/unavailable) are silently skipped

## Acceptance Criteria

- [ ] Up/down buttons visible on each VPN card
- [ ] Reordering works and is visually immediate
- [ ] Order persists across app restarts
- [ ] New VPNs appear at the end without disrupting existing order
- [ ] Existing tests pass; new tests cover ordering logic
