## Validation Report: Bluetooth D-Bus Naming Fix (v11.7)
**Date**: 2026-02-14
**Status**: PASSED

### Phase 3: Tests
- Test suite: `python3 -m pytest test_headset_control.py test_mic_association.py -v`
- Results: 7 passing, 0 failing
- Status: PASSED

### Phase 4: Code Quality
- Dead code: None found (old `run_command` fully replaced by `_run_bluetoothctl`)
- Duplication: None found
- Encapsulation: Clean separation (D-Bus for queries, bluetoothctl for actions)
- Status: PASSED

### Phase 5: Security Review
- D-Bus SystemBus access is standard for BlueZ integration, no elevation needed
- No user input flows into D-Bus queries (MAC addresses come from BlueZ itself)
- No credential exposure
- Status: PASSED

### Phase 5.5: Release Safety
- Change type: Code-only (bug fix)
- Rollback plan: Revert commit, redeploy
- Status: PASSED

### Root Cause Analysis
- `bluetoothctl` 5.86 changed behavior: non-interactive `bluetoothctl devices` returns empty
- PipeWire bluez5 integration sets `device.alias` to `(null)` for BT devices
- Both name resolution paths failed, causing MAC addresses to display instead of names
- D-Bus `org.bluez.Device1` properties still have correct Name/Alias values

### Changes
1. `BluetoothController.get_devices()`: Replaced `bluetoothctl` CLI parsing with D-Bus `GetManagedObjects()` call
2. `get_sinks()`: Fixed `device.api` check (`'bluez' in` vs `== 'bluez'`), added `device.alias` fallback
3. `get_sources()`: Added `bluez.alias`/`device.alias` fallback for mic name resolution
4. Added `import dbus` dependency
5. Updated README: added `python-dbus` to dependencies, v11.7 changelog entry
6. Updated About dialog version to 11.7

### Overall
- All gates passed: YES
- Smoke test confirmed: "Papa's AirPods Pro" displays correctly for both sink and source
