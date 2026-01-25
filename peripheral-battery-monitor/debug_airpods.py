
import subprocess
import re
from dataclasses import dataclass
from typing import Optional

@dataclass
class BatteryInfo:
    level: int
    status: str
    voltage: Optional[float]
    device_name: str

def get_airpods_battery():
    print("--- Debugging AirPods Logic ---")
    
    # 1. Find the AirPods MAC address
    mac = None
    name = "AirPods"
    try:
        devices_out = subprocess.run(['bluetoothctl', 'devices'], capture_output=True, text=True).stdout
        print(f"DEBUG: 'bluetoothctl devices' output:\n{devices_out}")
        
        for line in devices_out.split('\n'):
            if "AirPods" in line:
                print(f"DEBUG: Found matching line: {line}")
                parts = line.split()
                if len(parts) >= 2:
                    mac = parts[1]
                    # Extract name (rest of line)
                    name_parts = line.split(' ', 2)
                    if len(name_parts) > 2:
                        name = name_parts[2]
                    break
    except Exception as e:
        print(f"DEBUG: Error finding devices: {e}")
        pass

    if not mac:
        print("DEBUG: No MAC found for 'AirPods'")
        return None

    print(f"DEBUG: MAC found: {mac}")

    # 2. Get Info
    try:
        info_out = subprocess.run(['bluetoothctl', 'info', mac], capture_output=True, text=True).stdout
        print(f"DEBUG: 'bluetoothctl info {mac}' output:\n{info_out}")
        
        # Check connection first
        if "Connected: yes" not in info_out:
            print("DEBUG: 'Connected: yes' not found in output. Returning None.")
            return None # Disconnected
            
        print("DEBUG: Device is Connected.")

        match = re.search(r'Battery Percentage:\s+(0x[0-9a-fA-F]+|\d+)', info_out)
        if match:
            val_str = match.group(1)
            level = int(val_str, 16) if val_str.startswith('0x') else int(val_str)
            print(f"DEBUG: Battery found: {level}")
            return BatteryInfo(
                level=level,
                status="Discharging", # Assumption
                voltage=None,
                device_name=name
            )
            
        print("DEBUG: No battery level found. Returning Connected/-1.")
        return BatteryInfo(
            level=-1, # Signal for "Unknown Level"
            status="Connected",
            voltage=None,
            device_name=name
        )
        
    except Exception as e:
        print(f"DEBUG: Error getting info: {e}")
        pass
        
    return None

if __name__ == "__main__":
    res = get_airpods_battery()
    print(f"RESULT: {res}")
