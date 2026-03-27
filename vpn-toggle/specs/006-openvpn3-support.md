# Spec 006: OpenVPN3 Backend Support

**Status**: INCOMPLETE

## Overview

Add OpenVPN3 as a second VPN backend alongside NetworkManager, allowing vpn-toggle to discover, connect, disconnect, monitor, and health-check OpenVPN3 sessions managed by the `openvpn3` daemon.

## Motivation

The `aiqlabs-vpn-toggle` script already manages an OpenVPN3 VPN, but as a standalone bash script with no health monitoring, metrics, or GUI. Meanwhile, vpn-toggle has a mature monitoring stack (health asserts, metrics, graphing, system tray) but only speaks NetworkManager/nmcli. Unifying these means:

- One tool to manage all VPN connections regardless of backend
- OpenVPN3 VPNs get the same health monitoring, auto-bounce, and metrics that NM VPNs already have
- The separate `aiqlabs-vpn-toggle` script can eventually be retired

## Background: OpenVPN3 on This System

- **Version**: OpenVPN3/Linux v26
- **CLI**: `openvpn3` (session-start, session-manage, sessions-list, configs-list, session-stats)
- **D-Bus services**: `net.openvpn.v3.configuration`, `net.openvpn.v3.sessions`, `net.openvpn.v3.backends`
- **Existing config**: `aiqlabs` profile with web-based OIDC authentication
- **Key difference from NM**: OpenVPN3 manages its own tunnel independently of NetworkManager. Sessions are identified by config name, not NM connection profile.

## Design Decisions

### CLI vs D-Bus

Use the `openvpn3` CLI (subprocess), not D-Bus directly.

**Rationale**: vpn-toggle already uses subprocess for nmcli. The openvpn3 CLI is the stable public interface, and using it keeps the implementation consistent with the existing nmcli pattern. D-Bus would add a `dbus-python` or `dasbus` dependency for marginal benefit. The CLI supports `--json` output for session-stats, making structured parsing straightforward where needed.

### Backend Abstraction

Introduce a `VPNBackend` protocol (or ABC) that both `NMBackend` and `OpenVPN3Backend` implement. The existing `VPNManager` becomes a facade that delegates to the appropriate backend based on the VPN's configured `backend` field.

This keeps the rest of the codebase (monitor, asserts, GUI, metrics) unaware of which backend a VPN uses.

### Authentication Handling

OpenVPN3 connections may require interactive web authentication (OIDC). The connect operation must:

1. Launch `openvpn3 session-start --config <name>` (which may open a browser)
2. Poll for "Client connected" status with a configurable timeout (default: 60s)
3. Report success/failure/timeout back through the same `Tuple[bool, str]` interface

This is inherently slower than nmcli connect and may require user interaction. The GUI should indicate "Awaiting authentication..." during this window.

## Phase 0: Codebase Modularization (Pre-requisite)

Before introducing the backend abstraction, split oversized modules to keep each file focused on a single responsibility. This is a separate commit (or commits) from the OpenVPN3 feature work.

### gui.py Split (962 lines → ~4 modules)

`gui.py` is a God module with 4 classes and 40 methods mixing UI layout, business logic coordination, tray management, and state persistence.

- [ ] Extract `tray.py` — `TrayManager` class: tray icon setup, context menu, activation handler, tooltip updates, close-to-tray logic (currently lines ~700-771 of gui.py)
- [ ] Extract `widgets.py` — `VPNWidget` class: single VPN card UI component with status display and connection timer (currently lines ~30-250 of gui.py)
- [ ] Extract `dialogs.py` — `VPNConfigDialog` and `SettingsDialog` classes: configuration and settings dialogs (currently lines ~252-530 of gui.py)
- [ ] `gui.py` retains only `VPNToggleMainWindow`, importing from the extracted modules. Target: under 500 lines

### models.py Extraction

- [ ] Extract `models.py` — `VPNConnection` and `VPNStatus` dataclasses from `vpn_manager.py`, so both backends can import them without circular dependencies

### Modules That Stay As-Is

These are well-structured and under 260 lines — no changes needed:

- `asserts.py` (256 lines) — clean class hierarchy with factory pattern
- `metrics.py` (206 lines) — focused data collection and persistence
- `graph.py` (234 lines) — pure visualization, no business logic
- `utils.py` (81 lines) — shared utilities
- `config.py` (323 lines) — borderline but cohesive around a single config file; may grow with new fields but splitting the lock coordination isn't worth the complexity
- `monitor.py` (342 lines) — complex but cohesive around monitoring state machine; splitting would fragment the state machine logic

### Test Updates

- [ ] Existing tests must be updated for new import paths (moved classes)
- [ ] All 149 existing tests must pass after modularization, before any OpenVPN3 code is added
- [ ] This is a pure refactor — no behavior changes

---

## Requirements

### Backend Protocol

- [ ] Define a `VPNBackend` protocol/ABC with methods: `list_vpns()`, `is_vpn_active()`, `get_vpn_status()`, `connect_vpn()`, `disconnect_vpn()`, `bounce_vpn()`, `get_connection_timestamp()`
- [ ] Return types match the existing `VPNConnection`, `VPNStatus` signatures
- [ ] Extract the current nmcli logic from `VPNManager` into an `NMBackend` class implementing the protocol
- [ ] `VPNManager` becomes a facade: it holds a registry of backends and dispatches calls based on the VPN's backend type

### OpenVPN3 Backend Implementation

- [ ] `OpenVPN3Backend` class implementing the `VPNBackend` protocol
- [ ] **Availability check**: Verify `openvpn3` binary exists at init (like nmcli check). If not present, the backend is unavailable — log a warning but do not crash
- [ ] **list_vpns()**: Run `openvpn3 configs-list` to discover available profiles, and `openvpn3 sessions-list` to determine which are active. Return `VPNConnection` objects with `connection_type="openvpn3"`
- [ ] **is_vpn_active()**: Check `openvpn3 sessions-list` for a session matching the config name with "Client connected" status
- [ ] **get_vpn_status()**: Return connected state. IP address extraction is best-effort (parse `session-stats --json` if available, otherwise omit)
- [ ] **connect_vpn()**: Run `openvpn3 session-start --config <name>`, poll `sessions-list` for "Client connected" status up to `auth_timeout_seconds` (default 60). Return `(True, msg)` on success, `(False, msg)` on timeout or error. Clean up pending sessions on timeout
- [ ] **disconnect_vpn()**: Run `openvpn3 session-manage --config <name> --disconnect`
- [ ] **bounce_vpn()**: Disconnect then reconnect (same pattern as NM bounce)
- [ ] **get_connection_timestamp()**: Best-effort from session-stats or return None

### Configuration Changes

- [ ] Add optional `"backend"` field to VPN config entries: `"networkmanager"` (default) or `"openvpn3"`
- [ ] Add optional `"auth_timeout_seconds"` field for openvpn3 VPNs (default: 60)
- [ ] Backward compatible: existing configs without `"backend"` field default to `"networkmanager"`
- [ ] Config version bump to `"2.1.0"`

Example VPN config entry:
```json
{
  "name": "aiqlabs",
  "display_name": "AIQ Labs VPN",
  "backend": "openvpn3",
  "auth_timeout_seconds": 60,
  "enabled": true,
  "asserts": [
    {
      "type": "dns_lookup",
      "hostname": "some-internal-host.aiqlabs.com",
      "expected_prefix": "10.",
      "description": "Verify internal DNS resolves"
    }
  ]
}
```

### GUI Changes

- [ ] VPN list should show backend type indicator (small label or icon distinguishing NM vs OpenVPN3 VPNs)
- [ ] During OpenVPN3 connect with pending auth, show "Awaiting authentication..." status instead of a frozen UI. The connect must run in a thread (existing pattern from NM connects)
- [ ] Auto-discovery: on startup (or refresh), query both backends and merge results into the VPN list. VPNs found by a backend but not in config should appear as unconfigured (same as current NM behavior)

### Monitor Integration

- [ ] Health asserts work identically for OpenVPN3 VPNs (DNS lookup, geolocation) — no changes needed since asserts are backend-agnostic
- [ ] Bounce action dispatches to the correct backend
- [ ] Metrics collection works unchanged (it only cares about assert results, not backend type)

### Startup Restore

- [ ] Connection restore on startup works for OpenVPN3 VPNs (calls the correct backend's connect_vpn)
- [ ] Restore list entries need no backend annotation — VPNManager looks up the backend from the VPN's config entry

### Error Handling

- [ ] If `openvpn3` binary is not installed, the OpenVPN3 backend is silently unavailable (no VPNs from that backend, no errors shown to user)
- [ ] Auth timeout produces a clear error message, not a hung UI
- [ ] Stale sessions (from crashed connections) should be cleaned up on disconnect: run `openvpn3 session-manage --cleanup` if disconnect fails

## Out of Scope

- **Config import**: Importing `.ovpn` files into openvpn3 via the GUI (use `openvpn3 config-import` manually)
- **Session pause/resume**: OpenVPN3 supports pause/resume but vpn-toggle has no pause concept today
- **D-Bus signal subscription**: Real-time session state changes via D-Bus signals (polling via CLI is sufficient for health check intervals of 30s+)
- **Replacing aiqlabs-vpn-toggle immediately**: That script can coexist; retirement is a follow-up task once this is stable

## Testing Strategy

- Unit tests for `OpenVPN3Backend` with subprocess mocking (same pattern as existing `test_vpn_manager.py`)
- Unit tests for `VPNManager` facade dispatch logic
- Integration tests that call real `openvpn3 configs-list` / `sessions-list` (skip if openvpn3 not installed)
- Existing NM tests must continue to pass unchanged (refactor must not break them)

## Rollback

Revert the commit. Config files with `"backend": "openvpn3"` entries will be ignored (treated as NM, which will fail gracefully since NM won't know the connection name). No data migration needed.

## Implementation Order

1. **Modularization commit(s)** — Phase 0 splits (gui.py, models.py extraction, backends/ directory). Pure refactor, all existing tests pass.
2. **Backend abstraction commit** — VPNBackend protocol, NMBackend extraction, VPNManager facade. Still NM-only, all tests pass.
3. **OpenVPN3 backend commit** — OpenVPN3Backend implementation, config schema changes, GUI updates, new tests.

Each step is independently committable and revertable.

## Acceptance Criteria

### Phase 0: Modularization

- [ ] `gui.py` split into `gui.py`, `tray.py`, `widgets.py`, `dialogs.py` — each under 500 lines
- [ ] `models.py` contains `VPNConnection` and `VPNStatus` dataclasses
- [ ] All existing tests pass with updated import paths
- [ ] No behavior changes — pure refactor

### Phase 1: Backend Abstraction

- [ ] `backends/` package exists with `__init__.py` (VPNBackend protocol), `nm.py` (NMBackend)
- [ ] `NMBackend` extracted from current `VPNManager` without behavior change
- [ ] `VPNManager` facade dispatches to correct backend based on config
- [ ] All existing tests pass

### Phase 2: OpenVPN3 Integration

- [ ] `OpenVPN3Backend` implements the protocol using `openvpn3` CLI
- [ ] Config schema supports `"backend"` and `"auth_timeout_seconds"` fields
- [ ] Existing NM VPN workflows (connect, disconnect, bounce, monitor, metrics) work identically
- [ ] OpenVPN3 VPNs can be connected, disconnected, bounced, and health-checked through the GUI
- [ ] Auth timeout is handled gracefully (no hung UI, clear error message)
- [ ] App starts and works normally when `openvpn3` is not installed
- [ ] New tests cover OpenVPN3Backend and VPNManager dispatch
