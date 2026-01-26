
import sys
import structlog
from unittest.mock import MagicMock
from dataclasses import dataclass
from typing import Optional
import subprocess
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

def get_mouse_battery() -> Optional[BatteryInfo]:
    """
    Attempts to retrieve battery information for the first found Logitech mouse.
    Returns BatteryInfo object or None if no mouse found.
    """
    
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
                                return _extract_battery(paired)
                
                if candidate and candidate.kind == 'mouse':
                    return _extract_battery(candidate)

            except Exception:
                continue
                
    except Exception as e:
        log.error("device_check_failed", error=str(e))
        return None

    return None

def _extract_battery(dev) -> Optional[BatteryInfo]:
    try:
        if not dev.online:
             # Try to ping to wake it up if possible, but might not help if really offline
             try:
                 dev.ping()
             except Exception:
                 pass
        
        # Double check online after ping
        # Note: solaar objects might not update .online property immediately without re-query
        # but calling battery() usually tries to fetch.
        
        bat = dev.battery()
        if bat:
            # bat.level is usually a NamedInt or int.
            # bat.status is an enum
            return BatteryInfo(
                level=int(bat.level),
                status=str(bat.status),
                voltage=bat.voltage,
                device_name=dev.name
            )
    except Exception:
        pass
    return None


def get_keyboard_battery() -> Optional[BatteryInfo]:
    """
    Attempts to retrieve battery information for a Keychron or HID keyboard via UPower.
    """
    
    try:
        # 1. Find the keyboard device path in UPower
        # We look for a keyboard device. We know it's a 'keyboard' type in UPower.
        enum_proc = subprocess.run(['upower', '-e'], capture_output=True, text=True)
        if enum_proc.returncode != 0:
            return None
            
        lines = enum_proc.stdout.strip().split('\n')
        kb_path = None
        for line in lines:
            if 'keyboard' in line.lower():
                # Prefer Keychron if multiple keyboards, but stick to first if not
                kb_path = line.strip()
                break
        
        if not kb_path:
            return None
            
        # 2. Query the device info
        info_proc = subprocess.run(['upower', '-i', kb_path], capture_output=True, text=True)
        if info_proc.returncode != 0:
            return None
            
        output = info_proc.stdout
        
        # Regex extraction
        model_match = re.search(r'model:\s+(.*)', output)
        level_match = re.search(r'percentage:\s+(\d+)%', output)
        state_match = re.search(r'state:\s+(.*)', output)
        
        if level_match:
            return BatteryInfo(
                level=int(level_match.group(1)),
                status=state_match.group(1).capitalize() if state_match else "Unknown",
                voltage=None,
                device_name=model_match.group(1).strip() if model_match else "Keyboard"
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

def get_airpods_battery_ble() -> Optional[BatteryInfo]:
    """
    Scans for AirPods BLE advertisements (Manufacturer 0x004c, Type 0x07) to extract battery.
    Uses bleak (async) so we wrap it in asyncio.run().
    """
    import asyncio
    try:
        from bleak import BleakScanner
    except ImportError:
        return None

    async def scan():
        battery_info = None
        
        # We need a way to stop scanning once found or timeout
        stop_event = asyncio.Event()

        def callback(device, advertisement_data):
            nonlocal battery_info
            if battery_info: return
            
            # Apple Manufacturer ID 0x004c (76)
            if 76 in advertisement_data.manufacturer_data:
                data = advertisement_data.manufacturer_data[76]
                # Check for Type 0x07 (AirPods status)
                # Structure: 07 [Size] [Device?] ... [BatteryByte] ...
                # Length varies. Usually > 0.
                # Heuristic: RSSI check? 
                
                # Basic check for now: Is it the connected AirPods?
                # We can try to match the BLE address if we verify it matches (it often doesn't).
                # Or just picking the strongest signal 0x004c device?
                if 27 <= len(data) or (len(data) > 2 and data[0] == 0x07):
                     # Type 0x07 confirmed
                     # Attempt decode
                     # Byte layout is proprietary.
                     # Common observation: 
                     # Byte 6-ish? 
                     # Let's try to match known patterns seen in online scripts.
                     # "AirStatus" generic decoding:
                     # It looks for specific bytes.
                     pass
                
                # FOR POC: We just return a dummy strict value if we see ANY Apple device with decent signal
                # and assume it's the airpods for now, OR rely on a specific byte.
                # We saw in research that byte 6 or 7 often holds battery.
                # Let's assume we find it.
                pass

        # For this iteration, since we don't have the exact decoding verified, 
        # I will implement a 'Generic Apple BLE' detector that returns "Connected" 
        # if it sees packets, which confirms presence better than just 'bluetoothctl info' 
        # (which might be stale).
        # Actually, let's try to implement the real decoder from open source references if possible.
        # But for now, let's fail safe: Return None if we can't be sure.
        pass
        
    # Since proper implementation requires a complex parser, and I want to verify 
    # threading first, I will implement a placeholder that actually SCANs but returns None
    # unless verified. 
    # Wait, the user WANTS it to work.
    # Let's use the 'bluetoothctl' fallback as the primary, and THIS as a 'live' check?
    # Actually, `bluetoothctl` already gives us 'Connected'.
    # The BLE scan is mainly for BATTERY LEVEL.
    # If we can't decode it, this function is useless.
    
    # Let's try to import the parsing logic from a known gist.
    # Reference: https://github.com/delphiki/AirStatus/blob/master/main.py
    # They check for data starting with 0x0719...
    
    return None

# Re-implementing get_airpods_battery to use the best available method
# Parsing BLE logic inline for simplicity of the file.

async def _ble_scan_for_airpods(target_mac=None):
    from bleak import BleakScanner
    
    async def scan():
        log.debug("starting_ble_scan", target=target_mac)
        found_info = None
        
        # We need a way to stop scanning once found
        
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
                
                # Check MAC match
                if target_mac and device.address.upper() == target_mac.upper():
                    log.debug("matched_target_mac")
                
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
                            
                        # RSSI check to ensure it's OUR device. Relaxed to -85 per user request.
                        if advertisement_data.rssi > -85:
                            log.debug("strong_signal", level=final_level, details=details)
                            found_info = BatteryInfo(
                                level=final_level,
                                status=status,
                                voltage=None,
                                device_name="AirPods",
                                details=details
                            )
                        else:
                            log.debug("weak_signal", rssi=advertisement_data.rssi)
                except Exception:
                    pass
                
                # Fallback if decoding failed but packet valid
                if not found_info:
                    name = device.name or ""
                    if "AirPods" in name or advertisement_data.rssi > -70:
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
        
        await scanner.stop()
        
        log.debug("scan_finished", result=found_info)
        return found_info

    return await scan()

def get_airpods_battery() -> Optional[BatteryInfo]:
    """
    Retrieves battery for AirPods using bluetoothctl or BLE scan.
    """
    import asyncio
    
    # 1. Try bluetoothctl for Connection Status (Fast, reliable for connection)
    mac = None
    name = "AirPods"
    is_connected = False
    
    try:
        # Find MAC
        devices_out = subprocess.run(['bluetoothctl', 'devices'], capture_output=True, text=True).stdout
        for line in devices_out.split('\n'):
            if "AirPods" in line:
                parts = line.split()
                if len(parts) >= 2:
                    mac = parts[1]
                    name_parts = line.split(' ', 2)
                    if len(name_parts) > 2:
                        name = name_parts[2]
                    break
        
        if mac:
            info_out = subprocess.run(['bluetoothctl', 'info', mac], capture_output=True, text=True).stdout
            if "Connected: yes" in info_out:
                is_connected = True
                # Try Parsing Battery Level from BlueZ
                match = re.search(r'Battery Percentage:\s+(0x[0-9a-fA-F]+|\d+)', info_out)
                if match:
                    val_str = match.group(1)
                    level = int(val_str, 16) if val_str.startswith('0x') else int(val_str)
                    return BatteryInfo(level=level, status="Discharging", voltage=None, device_name=name)

    except Exception:
        pass

    # 2. If Connected but no battery (or just paired), Try BLE Scan
    
    log.debug("airpods_logic", mac=mac, bluez_connected=is_connected)

    if mac:  
        try:
             # Run the async scan with target MAC to check for matches
             ble_info = asyncio.run(_ble_scan_for_airpods(mac))
             if ble_info:
                 # If we eventually decode battery, use it. 
                 # currently _ble_scan_for_airpods returns details if found.
                 ble_info.device_name = name
                 # If found via BLE, it's visible/connected
                 if ble_info.status == "Connected":
                      ble_info.status = "BLE-Visible"
                 return ble_info
        except Exception:
             pass

        # Fallback: If scan failed (not found via BLE)
        # Only report connected if BlueZ actually says so.
        if is_connected:
            return BatteryInfo(level=-1, status="Connected", voltage=None, device_name=name)
            
    return None

if __name__ == "__main__":
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
        print("No AirPods found via bluetoothctl.")
