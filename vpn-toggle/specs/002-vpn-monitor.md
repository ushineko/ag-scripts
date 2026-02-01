# Spec 002: VPN Monitor Mode (v2.0)

**Status: IN PROGRESS**

## Description
Major iteration of vpn-toggle adding integrated monitor mode with assert-based health checking, persistent GUI for all VPNs, and auto-reconnect capabilities.

## Requirements

### Core Functionality (Retained from v1.0)
- Manual VPN bounce/restart capability
- NetworkManager (nmcli) integration
- Desktop notifications

### New Features (v2.0)
1. **Persistent GUI** showing ALL VPNs (replacing single-VPN popup)
2. **Monitor Mode** with assert-based health checking
   - Runs asserts on configurable timer (default: 120s interval)
   - Auto-reconnects on assert failure
   - Disables VPN after failure threshold (default: 3 failures)
   - Optional (can be disabled per-VPN or globally)
   - Grace period after connection before first check (default: 15s)
3. **Assert Types**
   - **DNS Lookup**: Verify DNS resolution matches expected IP prefix (partial match support)
   - **Geolocation**: Verify IP originates from expected location (using ip-api.com)
   - Both, one, or neither can be enabled per VPN
4. **Configuration Persistence**
   - VPN configurations and assert settings
   - Window position/geometry
   - Monitor state and preferences
   - Stored in `~/.config/vpn-toggle/config.json`
5. **Backward Compatibility**
   - Accept legacy hotkey arguments (VPN name) but swallow/ignore
   - Always show full GUI regardless of arguments

## Architecture

### Technology Stack
- **Language**: Python 3.8+
- **GUI Framework**: PyQt6
- **VPN Control**: NetworkManager (nmcli)
- **Geolocation API**: ip-api.com (free, no API key)
- **Testing**: pytest

### Components
1. **ConfigManager** - JSON configuration load/save
2. **VPNManager** - nmcli wrapper for VPN operations
3. **Assert System** - DNS lookup + geolocation checks
4. **MonitorThread** - Background monitoring with state machine
5. **Main GUI** - PyQt6 window showing all VPNs
6. **Entry Point** - Argument parsing and legacy compatibility

## Acceptance Criteria

### Core Infrastructure
- [ ] Package structure created (vpn_toggle/ directory)
- [ ] ConfigManager loads/saves JSON config
- [ ] ConfigManager provides defaults when config doesn't exist
- [ ] ConfigManager thread-safe (uses locking)
- [ ] Logging setup (file + console)
- [ ] Config tests pass (pytest tests/test_config.py)

### VPN Management
- [ ] VPNManager lists all VPN connections via nmcli
- [ ] VPNManager gets VPN status (connected/disconnected)
- [ ] VPNManager connects VPN
- [ ] VPNManager disconnects VPN
- [ ] VPNManager bounces VPN (disconnect + connect)
- [ ] VPN operations logged
- [ ] VPN manager tests pass (pytest tests/test_vpn_manager.py)

### Assert System
- [ ] DNS lookup assert implemented (socket.gethostbyname)
- [ ] DNS assert supports partial IP prefix matching (e.g., "100.")
- [ ] Geolocation assert implemented (ip-api.com)
- [ ] Geolocation assert prints detected location for debugging
- [ ] Geolocation assert supports field selection (city, region, country)
- [ ] Assert factory creates asserts from config
- [ ] Assert tests pass (pytest tests/test_asserts.py)

### Monitor Thread
- [ ] MonitorThread runs in background (QThread)
- [ ] Monitor checks asserts on configured interval (120s default)
- [ ] Monitor respects grace period after connection (15s default)
- [ ] Monitor tracks failures per VPN
- [ ] Monitor auto-reconnects on assert failure
- [ ] Monitor disables VPN after failure threshold (3 default)
- [ ] Monitor emits PyQt signals for GUI updates
- [ ] Monitor tests pass (pytest tests/test_monitor.py)

### GUI Implementation
- [ ] Main window displays all VPNs in list
- [ ] VPN list shows status (connected/disconnected)
- [ ] VPN list shows assert status (X/Y passing)
- [ ] VPN list shows last check time
- [ ] Manual connect button works
- [ ] Manual disconnect button works
- [ ] Manual bounce button works
- [ ] Monitor enable/disable toggle works
- [ ] Activity log displays monitor events
- [ ] Activity log auto-scrolls to bottom
- [ ] Window geometry saved on close
- [ ] Window geometry restored on open
- [ ] Settings dialog allows configuring asserts
- [ ] Settings dialog allows configuring monitor timing

### Integration & Testing
- [ ] Main entry point (vpn_toggle_v2.py) implemented
- [ ] Legacy arguments swallowed/ignored gracefully
- [ ] --debug flag enables debug logging
- [ ] install.sh creates desktop file
- [ ] install.sh makes scripts executable
- [ ] uninstall.sh removes desktop file
- [ ] README.md updated with v2.0 features
- [ ] Root README.md updated with vpn-toggle description
- [ ] All pytest tests pass
- [ ] Manual VPN operations work (connect/disconnect/bounce)

### End-to-End Verification
- [ ] Monitor mode auto-reconnects on assert failure
- [ ] Monitor mode alerts and disables after failure threshold
- [ ] DNS assert correctly matches partial IP prefixes
- [ ] Geolocation assert prints detected location
- [ ] Configuration persists across restarts
- [ ] Window geometry persists across restarts
- [ ] Legacy hotkey arguments are swallowed gracefully

## Implementation Notes

### Design Decisions
- **PyQt6** for GUI (polished, feature-rich)
- **Integrated monitoring thread** (not separate daemon)
- **ip-api.com** for geolocation (free, no API key)
- **Conservative timing defaults** (120s interval, 15s grace, 3 failures)

### Critical Files
1. `vpn_toggle/monitor.py` - Core monitor thread with state machine
2. `vpn_toggle/gui.py` - Main window and user interface
3. `vpn_toggle/asserts.py` - Assert implementations
4. `vpn_toggle/config.py` - Configuration management
5. `vpn_toggle_v2.py` - Main entry point

### Dependencies
- PyQt6 (`pip install PyQt6`)
- requests (`pip install requests`)
- pytest (`pip install pytest`)
- NetworkManager (nmcli command)

### Migration from v1.0
- Keep `toggle_vpn.sh` for reference (mark as deprecated)
- No automatic config migration (fresh start)
- Legacy hotkey bindings still work (launch full GUI)

## Testing Strategy
- Unit tests for all components (config, vpn_manager, asserts, monitor)
- Mocked network calls for assert tests
- Mocked subprocess calls for vpn_manager tests
- Manual testing with real VPN connections
- End-to-end verification of monitor auto-reconnect flow

## Completion Checklist
- [ ] All acceptance criteria checked
- [ ] All pytest tests pass
- [ ] Manual testing completed successfully
- [ ] Documentation updated (README.md)
- [ ] Install/uninstall scripts tested
- [ ] Changes committed to git
