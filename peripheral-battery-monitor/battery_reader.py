
import sys
import logging
from unittest.mock import MagicMock
from dataclasses import dataclass
from typing import Optional

# Configure basic logging
logging.basicConfig(level=logging.ERROR)

@dataclass
class BatteryInfo:
    level: int
    status: str
    voltage: Optional[float]
    device_name: str


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
             print(f"Error: Could not import solaar 'logitech_receiver' library even after mocking. Is solaar installed? Details: {e}", file=sys.stderr)
             return None
    except Exception as e:
         # Some other error during import (like the GI error we saw)
         print(f"Initial import failed with: {e}. Retrying with mocks...", file=sys.stderr)
         _setup_mocks()
         try:
            from logitech_receiver import base, device, receiver
         except ImportError as e:
            print(f"Error checking devices after mocking: {e}", file=sys.stderr)
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
        print(f"Error checking devices: {e}", file=sys.stderr)
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
    import subprocess
    import re
    
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
