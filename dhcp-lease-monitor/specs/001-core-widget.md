# Spec 001: DHCP Lease Monitor — Core Widget

**Status**: COMPLETE

## Overview

A frameless, always-on-top desktop widget (PyQt6) that displays real-time DHCP lease state from the local dnsmasq server. Leases are sorted most-recent-first. Clicking a lease opens a popup with detailed information. The widget follows the same UI architecture as `peripheral-battery-monitor`.

## System Context

- **DHCP server**: dnsmasq 2.92 on CachyOS
- **Lease file**: `/var/lib/misc/dnsmasq.leases` (world-readable, atomically written by dnsmasq)
- **Lease format**: `<expiry_epoch> <mac_address> <ip_address> <hostname> <client_id>` (space-delimited, one line per lease)
- **Subnet**: 192.168.86.0/24 on interface `eno2`
- **Lease time**: 24 hours
- **Typical lease count**: ~10 devices

There is also a libvirt dnsmasq instance serving VMs on `virbr0` (192.168.122.0/24) with a JSON lease file at `/var/lib/libvirt/dnsmasq/virbr0.status`. This is out of scope for v1.0 but the architecture should not preclude adding it later.

**CRITICAL**: This is a read-only monitoring tool. It must NEVER modify dnsmasq configuration, lease files, or any system state. If any future feature requires system modification, the user must be warned with unmistakable, alarming UI before proceeding.

---

## Data Source

### Lease File Parsing

Read and parse `/var/lib/misc/dnsmasq.leases`. Each line contains 5 space-delimited fields:

| Field | Example | Notes |
|-------|---------|-------|
| Expiry (epoch) | `1771454360` | Unix timestamp when lease expires. `0` = static/infinite lease |
| MAC address | `ac:ae:19:42:56:a8` | Lowercase, colon-separated |
| IP address | `192.168.86.68` | IPv4 dotted-quad |
| Hostname | `Yrmom` | `*` if not provided by client |
| Client ID | `01:5c:47:5e:76:c3:c6` | `*` if not provided. Often `01:<mac>` for Ethernet |

### Update Strategy

Use a hybrid approach for responsiveness without waste:

1. **inotify watch** on `/var/lib/misc/dnsmasq.leases` via Python's `inotify_simple` or `pyinotify` — triggers a re-read whenever dnsmasq writes the file
2. **Fallback QTimer** at 30-second intervals — catches cases where inotify misses an event (e.g., after suspend/resume)
3. **De-bounce**: If inotify fires multiple times within 500ms (dnsmasq may write rapidly during a burst of DHCP activity), coalesce into a single re-read

The lease file is <1 KB for ~10 devices. Re-reading it is negligible system cost.

### Data Model

```python
@dataclass
class DhcpLease:
    expiry: int              # Unix epoch (0 = static)
    mac: str                 # Lowercase MAC, colon-separated
    ip: str                  # IPv4 address
    hostname: str            # Client hostname ("*" → display as "Unknown")
    client_id: str           # Client identifier ("*" → None)
    vendor: str              # OUI vendor name (resolved from MAC prefix)
    device_type: str         # Inferred category: "phone", "laptop", "tablet", "printer", "tv", "desktop", "iot", "unknown"
    is_expired: bool         # True if current time > expiry
    time_remaining: int      # Seconds until expiry (0 if expired or static)
```

---

## Device Identification

### MAC OUI Vendor Lookup

Use the `mac-vendor-lookup` library for offline OUI resolution. The library bundles the IEEE OUI database and requires no network access.

- First 3 octets (24-bit prefix) → vendor name
- Example: `ac:ae:19` → could be "Unknown" (randomized MAC), `4c:e1:73` → "Apple, Inc."
- Randomized/private MACs (bit 1 of first octet set, i.e., locally administered) should be flagged as "Private MAC" rather than looked up

### Device Type Inference

Combine hostname patterns and OUI vendor to infer a device category. The inference is best-effort and displayed as a subtle hint (icon + tooltip), not authoritative.

**Heuristic priority** (first match wins):

| Signal | Pattern | Inferred Type | Icon |
|--------|---------|---------------|------|
| Hostname | contains `iphone` (case-insensitive) | phone | `phone` |
| Hostname | contains `ipad` | tablet | `tablet` |
| Hostname | contains `macbook`, `mbp`, `-laptop` | laptop | `laptop` |
| Hostname | contains `air` AND vendor is Apple | laptop | `laptop` |
| Hostname | starts with `NPI` | printer | `printer` |
| Hostname | contains `printer`, `laserjet`, `officejet` | printer | `printer` |
| Hostname | contains `tv`, `roku`, `firestick`, `chromecast`, `appletv` | tv/media | `video-display` |
| Hostname | contains `echo`, `alexa`, `google-home`, `homepod` | smart speaker | `audio-speakers` |
| Vendor | HP Inc, Hewlett, Canon, Epson, Brother | printer | `printer` |
| Vendor | Apple (and not matched above) | apple-generic | `computer-apple` (fallback to `computer`) |
| Vendor | Samsung, OnePlus, Xiaomi, Huawei (mobile vendors) | phone | `phone` |
| Vendor | Intel, Realtek, Qualcomm (NIC vendors) | desktop/laptop | `computer` |
| Private MAC | locally-administered bit set | private | `network-wireless` |
| Fallback | none of the above | unknown | `network-wired` |

Icons are sourced from the freedesktop icon theme via `QIcon.fromTheme()`. If a themed icon is missing, fall back to a generic `network-wired`.

### Device Type Icons — Visual Style

Each lease row displays a 20x20 icon from the freedesktop theme. The icon is placed to the left of the hostname/IP. Icon color follows the theme; no tinting is applied.

---

## UI Design

### Window

- **Frameless** + **translucent background** (same flags as peripheral-battery-monitor)
- **Always-on-top** via KWin rule (`aboverule=2`)
- **Position persistence** via KWin rule (`positionrule=4`)
- **Dragging** via `windowHandle().startSystemMove()` on left-click of the header area
- **Single instance** via `QLockFile`
- **Minimum width**: 320px
- **Maximum height**: 600px (scrolls if more leases)

### Layout

```
┌──────────────────────────────────────────────┐
│  DHCP Leases (9)                    ▼ eno2   │  ← Header row (drag target)
├──────────────────────────────────────────────┤
│  📱 iPhone              192.168.86.122       │  ← Lease row (clickable)
│     6e:be:93:2e:94:9a   expires in 18h 14m   │
├──────────────────────────────────────────────┤
│  💻 njv-mbp-m1          192.168.86.131       │
│     4c:e1:73:42:34:c9   expires in 18h 20m   │
├──────────────────────────────────────────────┤
│  ... (more rows, sorted by most recent       │
│       lease activity first)                  │
└──────────────────────────────────────────────┘
```

(The emoji above are illustrative. Actual rendering uses `QIcon.fromTheme()` icons.)

### Header Row

- **Title**: "DHCP Leases" + count in parentheses, e.g., "DHCP Leases (9)"
- **Interface indicator**: Right-aligned, shows the serving interface name (`eno2`)
- **Drag target**: Left-click anywhere on the header initiates window move

### Lease Row

Each lease is a clickable `QFrame` with hover highlight:

- **Line 1**: Device icon (20x20) + display name (hostname or "Unknown") + right-aligned IP address
- **Line 2**: MAC address (monospace, dimmed) + right-aligned time remaining ("expires in Xh Ym" or "EXPIRED" in red)
- **Sorting**: By expiry timestamp descending (most recently renewed/acquired first)
- **Expired leases**: Shown with dimmed text and strikethrough or reduced opacity. Sorted after active leases
- **Hover effect**: Subtle background color change (`rgba(255, 255, 255, 0.05)`)
- **Click**: Opens the detail popup (see below)

### Lease Detail Popup

Clicking a lease row opens a popup `QFrame` anchored near the clicked row (or near the widget edge if space is tight). The popup dismisses on:
- Click outside the popup
- Escape key
- Another lease row click (replaces popup)

**Popup contents** ("nerdy stats"):

| Field | Value | Notes |
|-------|-------|-------|
| Hostname | `Yrmom` | Or "Not provided" if `*` |
| IP Address | `192.168.86.68` | |
| MAC Address | `ac:ae:19:42:56:a8` | Monospace |
| MAC Type | `Globally unique` or `Locally administered (private)` | Based on bit 1 of first octet |
| OUI Vendor | `Apple, Inc.` | Or "Unknown vendor" |
| Device Type | `Phone (inferred)` | With confidence note |
| Lease Granted | `2026-02-17 11:19:20` | Calculated: expiry minus 24h lease time |
| Lease Expires | `2026-02-18 11:19:20` | Human-readable local time |
| Time Remaining | `23h 47m 12s` | Live countdown (updated every second while popup is open) |
| Client ID | `01:ac:ae:19:42:56:a8` | Or "Not provided" |

The popup should have a subtle dark background matching the main widget style, with a thin border and rounded corners.

### Scrolling

If the lease list exceeds the maximum widget height (600px), the list area becomes scrollable via `QScrollArea`. The scroll bar should be thin and styled to match the dark theme (custom `QScrollBar` stylesheet).

---

## Context Menu (Right-click)

| Item | Action |
|------|--------|
| **Opacity** | Submenu: 100% / 95% / 90% / 80% / 70% (radio group, persistent) |
| **Font Size** | Submenu: Small (0.8) / Medium (1.0) / Large (1.3) (radio group, persistent) |
| --- | separator |
| **Refresh Now** | Force re-read of lease file |
| **Copy IP** | (Only in lease right-click) Copy IP to clipboard |
| **Copy MAC** | (Only in lease right-click) Copy MAC to clipboard |
| --- | separator |
| **Quit** | Exit application |

---

## Settings

### Config File

Path: `~/.config/dhcp-lease-monitor.json`

```json
{
    "opacity": 0.95,
    "font_scale": 1.0,
    "lease_file": "/var/lib/misc/dnsmasq.leases",
    "lease_duration_hours": 24,
    "show_expired": true
}
```

- `lease_file`: Configurable path to accommodate non-default dnsmasq setups
- `lease_duration_hours`: Used to calculate "Lease Granted" time (expiry minus this value). Default matches dnsmasq config (24h)
- `show_expired`: Whether to display expired leases (dimmed) or hide them entirely

Settings are loaded at startup (merged with defaults) and saved immediately on any change via context menu.

### Window Position

Delegated entirely to KWin via `positionrule=4` (Apply Initially / Remember). Not stored in the JSON config.

---

## System Integration

### KWin Rule (`install_kwin_rule.py`)

Same pattern as peripheral-battery-monitor. Properties:

```ini
Description=DHCP Lease Monitor Always On Top
wmclass=dhcp-lease-monitor
wmclassmatch=1
above=true
aboverule=2
noborder=true
noborderrule=2
positionrule=4
sizerule=4
screenrule=4
```

Application must set `app.setDesktopFileName("dhcp-lease-monitor")` to match.

### Autostart

XDG `.desktop` file:

```ini
[Desktop Entry]
Type=Application
Name=DHCP Lease Monitor
Exec=/path/to/dhcp-lease-monitor.py
Icon=network-wired
StartupWMClass=dhcp-lease-monitor
Terminal=false
Categories=Utility;System;Network;
```

Installed to `~/.config/autostart/` and/or `~/.local/share/applications/` via `install.sh`.

### Single Instance

`QLockFile` at `QDir.tempPath() + "/dhcp-lease-monitor.lock"`.

---

## Logging

- **structlog** with rotating file handler at `~/.local/state/dhcp-lease-monitor/dhcp_lease_monitor.log`
- **Max size**: 5 MB, 1 backup
- **stderr redirect** to `~/.local/state/dhcp-lease-monitor/stderr.log`
- **faulthandler** enabled to `crash.log`
- **`--debug` flag**: Enables DEBUG-level console output

---

## CLI Arguments

| Argument | Effect |
|----------|--------|
| `--debug` | Enable verbose debug logging to console |
| `--lease-file PATH` | Override lease file path (overrides config) |

---

## Dependencies

| Package | Purpose | Install method |
|---------|---------|----------------|
| PyQt6 | UI framework | pip / system package |
| structlog | Structured logging | pip |
| mac-vendor-lookup | OUI vendor resolution | pip |
| inotify_simple | File change notifications | pip |

All are pure-Python except PyQt6. No system-level dependencies beyond what's already present on this CachyOS install.

---

## File Structure

```
dhcp-lease-monitor/
├── dhcp-lease-monitor.py          # Main Qt application
├── lease_reader.py                # Lease file parser + inotify watcher
├── device_identifier.py           # MAC OUI + hostname → device type inference
├── install_kwin_rule.py           # KWin always-on-top rule installer
├── install.sh                     # Interactive installer
├── uninstall.sh                   # Cleanup script
├── dhcp-lease-monitor.desktop     # XDG desktop entry
├── README.md                      # Documentation
├── specs/                         # Feature specs
│   └── 001-core-widget.md         # This spec
├── tests/                         # pytest tests
│   ├── test_lease_reader.py       # Lease parsing tests
│   └── test_device_identifier.py  # Device identification tests
└── validation-reports/            # Quality gate artifacts
```

---

## Acceptance Criteria

- [ ] Widget displays all active DHCP leases from `/var/lib/misc/dnsmasq.leases`
- [ ] Leases are sorted by most recent activity (expiry descending) with expired leases at the bottom
- [ ] Each lease row shows: device icon, display name (hostname or "Unknown"), IP address, MAC address, time remaining
- [ ] Clicking a lease row opens a detail popup with all nerdy stats (hostname, IP, MAC, vendor, device type, lease times, client ID)
- [ ] Detail popup shows a live countdown for time remaining
- [ ] Device type is inferred from MAC OUI vendor + hostname heuristics
- [ ] Appropriate freedesktop theme icon displayed per inferred device type
- [ ] Private/randomized MACs are identified and labeled
- [ ] Widget updates in real-time via inotify on the lease file, with 30s fallback timer
- [ ] Context menu provides: opacity control, font size control, refresh, copy IP/MAC, quit
- [ ] Settings (opacity, font scale, lease file path, lease duration, show_expired) persisted to `~/.config/dhcp-lease-monitor.json`
- [ ] Window is frameless, translucent, always-on-top (KWin rule)
- [ ] Window position remembered across restarts (KWin rule)
- [ ] Window is draggable via header area
- [ ] Single instance enforced via lock file
- [ ] Autostart via XDG `.desktop` file
- [ ] `install.sh` installs KWin rule, desktop entry, sets permissions
- [ ] `uninstall.sh` removes all installed artifacts
- [ ] `--debug` flag enables verbose console logging
- [ ] structlog-based logging with rotating file handler
- [ ] Expired leases shown dimmed (or hidden per setting)
- [ ] Scrollable when lease count exceeds widget height
- [ ] No system configuration is modified — read-only monitoring only
- [ ] Tests cover lease parsing, device identification heuristics, and expired lease handling

---

## Out of Scope (Future)

- Libvirt/virbr0 lease monitoring (separate dnsmasq instance)
- ARP ping / online status detection
- Historical lease tracking / lease history database
- Network scanning / port discovery
- DHCP event notifications (desktop notifications on new device join)
- Configurable heuristic rules via settings file
- Multiple lease file monitoring
