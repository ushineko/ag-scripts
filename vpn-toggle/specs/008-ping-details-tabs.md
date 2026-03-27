# Spec 008: Ping Assert, VPN Details, Tabbed Configure Dialog

**Status**: INCOMPLETE

## Overview

Three related enhancements to vpn-toggle:
1. A new "ping" health check assert type
2. A "Details" button showing live VPN interface and route info
3. Refactor the Configure dialog from flat layout to tabs

## 1. Ping Assert

### Motivation

DNS and geolocation asserts verify exit-point identity but not reachability of specific internal hosts. A ping assert lets users verify that a lab asset (e.g., `172.16.0.1`) is reachable through the VPN tunnel.

### Requirements

- [ ] New `PingAssert` class in `asserts.py` implementing `VPNAssert`
- [ ] Config fields: `host` (IP or hostname), `timeout_seconds` (default: 5)
- [ ] Uses `subprocess` to run `ping -c 1 -W <timeout> <host>`
- [ ] Returns pass if exit code 0, fail otherwise; message includes RTT on success
- [ ] Register in `create_assert()` factory as type `"ping"`
- [ ] Configurable in the Configure dialog (new tab — see section 3)

Example config:
```json
{
  "type": "ping",
  "host": "172.16.0.1",
  "timeout_seconds": 5,
  "description": "Ping lab gateway"
}
```

## 2. Details Button

### Motivation

Users need to see what interface, IP, and routes a VPN is using — especially when running multiple VPNs simultaneously.

### Requirements

- [ ] Add a "Details" button to each VPN card (in the button row)
- [ ] Only enabled when the VPN is connected
- [ ] Opens a read-only dialog showing:
  - Interface name (e.g., `tun0`)
  - Tunnel IP address
  - Routes pushed through the tunnel
- [ ] For NM VPNs: parse `nmcli connection show <name>` for IP4.ADDRESS and IP4.ROUTE
- [ ] For OpenVPN3 VPNs: find the tun device from `sessions-list`, then use `ip addr show <dev>` and `ip route show dev <dev>`
- [ ] Data is fetched fresh each time the dialog opens (not cached)

### Design

Add a `get_vpn_details(vpn_name) -> dict` method to each backend returning `{'interface': str, 'ip': str, 'routes': list[str]}`. The Details dialog is a simple read-only `QDialog` with a monospace `QTextEdit`.

## 3. Tabbed Configure Dialog

### Motivation

The Configure dialog currently has display name, enabled checkbox, DNS assert, and geolocation assert in a flat scrolling layout. Adding ping assert makes it too long. Tabs organize related settings.

### Requirements

- [ ] Replace the flat `VPNConfigDialog` layout with a `QTabWidget`
- [ ] Tab 1 — **General**: Display name, enabled checkbox
- [ ] Tab 2 — **Health Checks**: DNS assert, geolocation assert, ping assert (each in its own group box)
- [ ] Help text moves into the Health Checks tab
- [ ] Dialog minimum width stays at 500px
- [ ] `get_config()` collects from all tabs (same return format as before)

## Acceptance Criteria

- [ ] Ping assert works in the monitor (pass/fail with RTT in message)
- [ ] Details button shows interface, IP, and routes for connected VPNs
- [ ] Details button disabled when VPN is disconnected
- [ ] Configure dialog uses tabs (General, Health Checks)
- [ ] Ping assert configurable in Health Checks tab
- [ ] All existing tests pass; new tests cover PingAssert
