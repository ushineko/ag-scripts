
import sys
import structlog
import logging
import json
import dbus
from unittest.mock import MagicMock
from dataclasses import dataclass, asdict
from typing import Optional
import subprocess
import os
import re
import asyncio

log = structlog.get_logger()

@dataclass
class BatteryInfo:
    level: int
    status: str
    voltage: Optional[float]
    device_name: str
    ids: Optional[dict] = None # For internal use if needed
    details: Optional[dict] = None # For L/R/Case specific levels




def _setup_mocks():
    """
    Sets up mocks for gi and evdev if they are missing or broken.
    This is necessary because some environments have broken python bindings
    for these libraries when run from CLI, even if they exist.
    """
    # Add solaar path explicitly as it might not be in the default path for this user/env
    solaar_path = '/usr/lib/python3.14/site-packages'
    if solaar_path not in sys.path:
        sys.path.append(solaar_path)

    modules_to_mock = [
        'gi',
        'gi.repository',
        'gi.repository.GLib',
        'gi.repository.GObject',
        'evdev',
        'evdev.device',
        'evdev.ecodes',
        'evdev.util'
    ]
    
    for module in modules_to_mock:
        if module not in sys.modules:
             sys.modules[module] = MagicMock()

_CACHED_MOUSE = None

def get_mouse_battery() -> Optional[BatteryInfo]:
    """
    Attempts to retrieve battery information for the first found Logitech mouse.
    Returns BatteryInfo object or None if no mouse found.
    """
    global _CACHED_MOUSE
    
    if _CACHED_MOUSE:
        try:
             log.debug("using_cached_mouse")
             return _extract_battery(_CACHED_MOUSE)
        except Exception as e:
             log.warning("cached_mouse_failed_rescanning", error=str(e))
             _CACHED_MOUSE = None
    
    # Try importing normally first
    try:
        from logitech_receiver import base, device, receiver
    except ImportError:
        # If import fails, try patching modules and importing again
        _setup_mocks()
        try:
            from logitech_receiver import base, device, receiver
        except ImportError as e:
             log.error("solaar_import_failed", error=str(e))
             return None
    except Exception as e:
         # Some other error during import (like the GI error we saw)
         log.warning("initial_import_error", error=str(e))
         _setup_mocks()
         try:
            from logitech_receiver import base, device, receiver
         except ImportError as e:
            log.error("mock_import_failed", error=str(e))
            return None

    # Constants helper
    # We might need to map status enums to string if we can't import the constants/enums due to dependencies
    # But usually BatteryStatus is in common.py which is safe.
    
    try:
        # Solaar libraries are available now
        
        # Iterate through receivers and devices
        for dev_info in base.receivers_and_devices():
            try:
                candidate = None
                if dev_info.isDevice:
                    candidate = device.create_device(base, dev_info)
                else:
                    # It's a receiver
                    rec = receiver.create_receiver(base, dev_info)
                    if rec:
                        # Check paired devices
                        for paired in rec:
                            if paired and paired.kind == 'mouse':
                                # Found a mouse on this receiver
                                # We prioritize the first mouse we find for now
                                _CACHED_MOUSE = paired
                                log.info("new_mouse_cached", device=paired.name)
                                return _extract_battery(paired)
                
                if candidate and candidate.kind == 'mouse':
                    _CACHED_MOUSE = candidate
                    log.info("new_mouse_cached", device=candidate.name)
                    return _extract_battery(candidate)

            except Exception:
                continue
                
    except Exception as e:
        log.error("device_check_failed", error=str(e))
        return None

    return None

def _extract_battery(dev) -> Optional[BatteryInfo]:
    try:
        # Always ping before reading battery to ensure fresh device state.
        # This is especially important after state transitions (charging -> discharging)
        # where the device object may have stale internal state.
        try:
            dev.ping()
        except Exception:
            pass

        if not dev.online:
            log.debug("device_offline_after_ping", device=dev.name if hasattr(dev, 'name') else 'unknown')
            return None

        bat = dev.battery()
        if bat:
            return BatteryInfo(
                level=int(bat.level),
                status=str(bat.status),
                voltage=bat.voltage,
                device_name=dev.name
            )
    except Exception as e:
        log.debug("battery_extraction_failed", error=str(e))
    return None


def get_keyboard_battery() -> Optional[BatteryInfo]:
    """
    Attempts to retrieve battery information for a Keychron or HID keyboard.
    Prioritizes UPower (Bluetooth) for battery level, then Wired check, then 2.4G fallback.

    This ordering ensures that when the keyboard is plugged in for charging but still
    connected via Bluetooth, we show the actual battery percentage rather than "Wired".
    """

    # 1. Check UPower (Bluetooth) FIRST - prioritize actual battery readings
    # Standard UPower check for battery service
    try:
        # We look for a keyboard device. We know it's a 'keyboard' type in UPower.
        enum_proc = subprocess.run(['upower', '-e'], capture_output=True, text=True)
        if enum_proc.returncode == 0:
            lines = enum_proc.stdout.strip().split('\n')
            kb_path = None
            for line in lines:
                if 'keyboard' in line.lower():
                    # Prefer Keychron if multiple keyboards, but stick to first if not
                    kb_path = line.strip()
                    # If we find a Keychron in UPower, it's likely the Bluetooth one active
                    if "keychron" in kb_path.lower():
                         break

            if kb_path:
                # Query the device info
                info_proc = subprocess.run(['upower', '-i', kb_path], capture_output=True, text=True)
                if info_proc.returncode == 0:
                    output = info_proc.stdout

                    # Regex extraction
                    model_match = re.search(r'model:\s+(.*)', output)
                    level_match = re.search(r'percentage:\s+(\d+)%', output)
                    state_match = re.search(r'state:\s+(.*)', output)

                    # Only return if we actually got a level (implies Bluetooth battery reporting)
                    if level_match:
                        return BatteryInfo(
                            level=int(level_match.group(1)),
                            status=state_match.group(1).capitalize() if state_match else "Unknown",
                            voltage=None,
                            device_name=model_match.group(1).strip() if model_match else "Keyboard"
                        )
    except Exception:
        pass

    # 2. Check Wired Connection (Keychron K4 HE: 3434:0e40)
    # Only show "Wired" if no Bluetooth battery is available
    try:
        # Iterate over USB devices in sysfs
        usb_root = "/sys/bus/usb/devices"
        if os.path.exists(usb_root):
            for device in os.listdir(usb_root):
                dev_path = os.path.join(usb_root, device)
                try:
                    with open(os.path.join(dev_path, "idVendor"), "r") as f:
                        vid = f.read().strip()
                    with open(os.path.join(dev_path, "idProduct"), "r") as f:
                        pid = f.read().strip()

                    if vid == "3434" and pid == "0e40":
                        return BatteryInfo(
                            level=-1,
                            status="Wired",
                            voltage=None,
                            device_name="Keychron K4 HE"
                        )
                except (FileNotFoundError, OSError):
                    continue
    except Exception:
        pass

    # 3. Check Wireless/2.4G (Input Device Fallback)
    # If not Bluetooth (no UPower battery) and not Wired, but "Keychron" input device exists, assume 2.4G.
    try:
        with open("/proc/bus/input/devices", "r") as f:
            content = f.read()
            # Look for Keychron name (case insensitive)
            if re.search(r'N: Name=".*Keychron.*"', content, re.IGNORECASE):
                # We found the input device, but we fell through the UPower and Wired checks.
                # Use a distinct status so UI can handle it.
                return BatteryInfo(
                    level=-1,
                    status="Wireless", # Implies 2.4G
                    voltage=None,
                    device_name="Keychron K4 HE"
                )
    except Exception:
        pass

    return None

def get_headset_battery() -> Optional[BatteryInfo]:
    """
    Retrieves battery for SteelSeries headsets using headsetcontrol.
    """
    try:
        # headsetcontrol -b -c returns just the percentage number, or -1/error
        result = subprocess.run(
            ['headsetcontrol', '-b', '-c'], 
            capture_output=True, text=True
        )
        if result.returncode == 0:
            output = result.stdout.strip()
            # Check if output is a valid integer
            if output:
                try:
                    level = int(output)
                    # For Arctis via headsetcontrol:
                    # -1 often means charging/full, but practically often appears when off/disconnected 
                    # if checking via dongle. -2 is definitely disconnected.
                    # User requested "Disconnected" state (return None) for these cases.
                    if level < 0:
                        return None
                    
                    return BatteryInfo(
                        level=level,
                        status="Discharging",
                        voltage=None,
                        device_name="Arctis Headset"
                    )
                except ValueError:
                    pass
    except FileNotFoundError:
        pass # headsetcontrol not installed
    except Exception:
        pass
        
    return None

    return None

async def _ble_scan_for_airpods():
    from bleak import BleakScanner
    
    async def scan():
        log.debug("starting_ble_scan")
        found_info = None

        def callback(device, advertisement_data):
            nonlocal found_info
            if found_info: return
            
            # Apple ID
            if 76 not in advertisement_data.manufacturer_data:
                return
                
            data = advertisement_data.manufacturer_data[76]
            hex_data = data.hex()
            
            if hex_data.startswith('0719'):
                log.debug("found_apple_device", address=device.address, name=device.name, rssi=advertisement_data.rssi, raw=hex_data)

                try:
                    # Convert back to bytes for easier access
                    raw = bytes.fromhex(hex_data)
                    if len(raw) > 7:
                        # Parse Byte 6 (Left/Right)
                        b6 = raw[6]
                        
                        # Nibbles
                        right_val = (b6 >> 4) & 0x0F
                        left_val  = b6 & 0x0F
                        
                        # Parse Byte 7 (Case?)
                        b7 = raw[7]
                        case_val = b7 & 0x0F 
                        

                        log.debug("parsing_bytes", b6=hex(b6), left=left_val, right=right_val, b7=hex(b7), case=case_val)
                        
                        # Helper to convert 0-10 to %
                        def to_percent(v):
                            if v <= 10: return v * 10
                            if v == 15: return -1 # Disconnected/Charging?
                            return None
                            
                        l_pct = to_percent(left_val)
                        r_pct = to_percent(right_val)
                        c_pct = to_percent(case_val)
                        
                        details = {}
                        if l_pct is not None and l_pct >= 0: details['left'] = l_pct
                        if r_pct is not None and r_pct >= 0: details['right'] = r_pct
                        if c_pct is not None and c_pct >= 0: details['case'] = c_pct
                        
                        # Determine "Device Level" to show
                        levels = [p for p in [l_pct, r_pct] if p is not None and p >= 0]
                        
                        final_level = -1
                        status = "Connected"
                        
                        if levels:
                            final_level = min(levels) # Conservative
                            status = "Discharging"
                        elif c_pct is not None and c_pct >= 0:
                            final_level = c_pct
                            status = "Case Only"
                            
                        if advertisement_data.rssi > -70:
                            log.debug("strong_signal_candidate", level=final_level, details=details, rssi=advertisement_data.rssi, found_mac=device.address)
                            found_info = BatteryInfo(
                                level=final_level,
                                status=status,
                                voltage=None,
                                device_name="AirPods",
                                details=details
                            )
                        else:
                            log.debug("ignoring_weak_signal", rssi=advertisement_data.rssi, mac=device.address)
                except Exception:
                    pass
                
                # Fallback if decoding failed but packet valid
                if not found_info:
                    name = device.name or ""
                    # Only accept generic match if signal is very strong
                    if advertisement_data.rssi > -60:
                         found_info = BatteryInfo(
                            level=-1, 
                            status="Connected",
                            voltage=None,
                            device_name=name if name else "AirPods"
                         )

        scanner = BleakScanner(detection_callback=callback)
        await scanner.start()
        await asyncio.sleep(5.0)
        await scanner.stop()

        log.debug("scan_finished", result=found_info)
        return found_info

    return await scan()

def _find_airpods_via_dbus():
    """Find AirPods connection status and name via BlueZ D-Bus interface."""
    AUDIO_UUIDS = {
        '0000110b-0000-1000-8000-00805f9b34fb',  # Audio Sink
        '0000110d-0000-1000-8000-00805f9b34fb',  # Advanced Audio Distribution
    }
    try:
        bus = dbus.SystemBus()
        manager = dbus.Interface(
            bus.get_object('org.bluez', '/'),
            'org.freedesktop.DBus.ObjectManager'
        )
        objects = manager.GetManagedObjects()
    except dbus.exceptions.DBusException:
        return None, "AirPods", False

    for path, interfaces in objects.items():
        if 'org.bluez.Device1' not in interfaces:
            continue
        dev = interfaces['org.bluez.Device1']
        alias = str(dev.get('Alias', ''))
        name = str(dev.get('Name', ''))
        display_name = alias or name
        if 'airpods' not in display_name.lower():
            continue

        mac = str(dev.get('Address', ''))
        connected = bool(dev.get('Connected', False))
        icon = str(dev.get('Icon', ''))
        uuids = {str(u) for u in dev.get('UUIDs', [])}

        is_audio = bool(AUDIO_UUIDS & uuids) or icon.startswith('audio-')
        if is_audio:
            # Check for Battery1 interface on this device
            if 'org.bluez.Battery1' in interfaces:
                bat = interfaces['org.bluez.Battery1']
                level = int(bat.get('Percentage', -1))
                if level >= 0:
                    return mac, display_name, connected, level
            return mac, display_name, connected, None

    return None, "AirPods", False, None


def get_airpods_battery() -> Optional[BatteryInfo]:
    """Retrieves battery for AirPods via D-Bus connection check + BLE advertisement scan."""
    # 1. Check connection status via D-Bus (fast, stable)
    mac, name, is_connected, dbus_battery = _find_airpods_via_dbus()

    # If D-Bus has battery level directly (Battery1 interface), use it
    if dbus_battery is not None and dbus_battery >= 0:
        return BatteryInfo(level=dbus_battery, status="Discharging", voltage=None, device_name=name)

    log.debug("airpods_logic", mac=mac, dbus_connected=is_connected)

    # 2. Try BLE advertisement scan for granular L/R/Case battery
    if is_connected:
        try:
            ble_info = asyncio.run(_ble_scan_for_airpods())
            if ble_info:
                ble_info.device_name = name
                if ble_info.status == "Connected":
                    ble_info.status = "BLE-Visible"
                return ble_info
        except Exception:
            pass

        # Fallback: connected but no battery data available
        return BatteryInfo(level=-1, status="Connected", voltage=None, device_name=name)

    return None

def get_all_batteries() -> dict:
    results = {}
    
    # Mouse
    m = get_mouse_battery()
    if m: results['mouse'] = asdict(m)
    
    # Keyboard
    k = get_keyboard_battery()
    if k: results['kb'] = asdict(k)
    
    # Headset
    h = get_headset_battery()
    if h: results['headset'] = asdict(h)
    
    # AirPods
    a = get_airpods_battery()
    if a: results['airpods'] = asdict(a)
    
    return results

if __name__ == "__main__":
    # Ensure logs go to stderr so stdout is clean for JSON
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    if "--json" in sys.argv:
        print(json.dumps(get_all_batteries()))
        sys.exit(0)

    # Simple CLI test
    info = get_mouse_battery()
    if info:
        print(f"Mouse: {info.device_name} - {info.level}% ({info.status})")
    else:
        print("No Logitech mouse found.")
        
    info_kb = get_keyboard_battery()
    if info_kb:
        print(f"Keyboard: {info_kb.device_name} - {info_kb.level}% ({info_kb.status})")
    else:
        print("No keyboard found via UPower.")

    info_headset = get_headset_battery()
    if info_headset:
        print(f"Headset: {info_headset.device_name} - {info_headset.level}% ({info_headset.status})")
    else:
        print("No headset found via headsetcontrol.")

    info_airpods = get_airpods_battery()
    if info_airpods:
        print(f"AirPods: {info_airpods.device_name} - {info_airpods.level}% ({info_airpods.status})")
    else:
        print("No AirPods found.")
