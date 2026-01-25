
#!/usr/bin/env python3
import asyncio
import subprocess
import re
from bleak import BleakScanner

CMD_BLUETOOTHCTL = "bluetoothctl"

def check_connection_status():
    print(f"\n--- Checking 'bluetoothctl' status ---")
    mac = None
    try:
        devices_out = subprocess.run([CMD_BLUETOOTHCTL, 'devices'], capture_output=True, text=True).stdout
        for line in devices_out.split('\n'):
            if "AirPods" in line:
                print(f"Found Device Line: {line}")
                parts = line.split()
                if len(parts) >= 2:
                    mac = parts[1]
                    break
    except Exception as e:
        print(f"Error checking devices: {e}")
        return None

    if not mac:
        print("No AirPods found in paired devices.")
        return None

    try:
        info_out = subprocess.run([CMD_BLUETOOTHCTL, 'info', mac], capture_output=True, text=True).stdout
        if "Connected: yes" in info_out:
            print(f"Device {mac} is CONNECTED via BlueZ.")
            return mac
        else:
            print(f"Device {mac} is DISCONNECTED via BlueZ.")
            return None
    except Exception as e:
        print(f"Error getting info: {e}")
        return None

def decode_airpods_packet(hex_data, rssi):
    print(f"\n[Packet] RSSI: {rssi}, Data: {hex_data}")
    raw = bytes.fromhex(hex_data)
    
    # 1. Byte 0 Check
    if raw[0] != 0x07:
        print("  -> SKIPPED (Type is not 0x07)")
        return

    if len(raw) < 10:
        print("  -> SKIPPED (Too short)")
        return

    # 2. Decoding Attempt (Current Logic)
    print("  -> Decoding Candidate:")
    
    b6 = raw[6]
    right_val = (b6 >> 4) & 0x0F
    left_val = b6 & 0x0F
    
    b7 = raw[7]
    case_val = b7 & 0x0F
    
    def fmt_pct(v):
        if v <= 10: return f"{v*10}%"
        if v == 15: return "Disconnected/Charging"
        return f"Unknown({v})"
        
    print(f"     Byte 6 (0x{b6:02x}): Left={fmt_pct(left_val)}, Right={fmt_pct(right_val)}")
    print(f"     Byte 7 (0x{b7:02x}): Case={fmt_pct(case_val)}")
    
    # 3. Print full raw analysis for checking alternative offsets
    print("     Raw Dump:")
    line = []
    for i, b in enumerate(raw):
        line.append(f"{i:02d}: {b:02x}")
        if (i+1) % 10 == 0:
            print("       " + " ".join(line))
            line = []
    if line:
        print("       " + " ".join(line))

async def scan_ble():
    print(f"\n--- Scanning BLE for 10 seconds ---")
    
    def callback(device, advertisement_data):
        if 76 in advertisement_data.manufacturer_data: # 0x004c
            data = advertisement_data.manufacturer_data[76]
            # Verify if it's potentially AirPods
            # Check RSSI threshold? None for debug.
            # Check Name?
            name = device.name or "Unknown"
            
            # Filter for Type 0x07 (AirPods status)
            if len(data) > 0 and data[0] == 0x07:
                 decode_airpods_packet(data.hex(), advertisement_data.rssi)
            else:
                 # Debug: Found Apple device but not Type 0x07
                 # print(f"Found Apple Device {device.address} ({name}), but data starts with 0x{data[0]:02x}")
                 pass

    scanner = BleakScanner(detection_callback=callback)
    await scanner.start()
    print("Scanning... (20 seconds)")
    await asyncio.sleep(20.0)
    await scanner.stop()
    print("--- Scan Complete ---")

async def main():
    print("=== AirPods Flapping Debugger ===")
    print("Capturing ALL 0x07 packets to find the 'L:90' culprit.")
    
    # 2. Scan BLE
    await scan_ble()

if __name__ == "__main__":
    asyncio.run(main())
