import asyncio
import subprocess
from bleak import BleakScanner

def get_target_mac():
    try:
        devices_out = subprocess.run(['bluetoothctl', 'devices'], capture_output=True, text=True).stdout
        for line in devices_out.split('\n'):
            if "AirPods" in line:
                parts = line.split()
                if len(parts) >= 2:
                    return parts[1], line
    except Exception as e:
        print(f"Error getting target MAC: {e}")
    return None, None

async def scan(target_mac):
    print(f"Target MAC from bluetoothctl: {target_mac}")
    
    def callback(device, advertisement_data):
        if 76 in advertisement_data.manufacturer_data:
            data = advertisement_data.manufacturer_data[76]
            hex_d = data.hex()
            is_airpods = hex_d.startswith('07')
            print(f"FOUND Apple Device: {device.address} | RSSI: {advertisement_data.rssi} | Data: {hex_d}")
            if is_airpods:
                print(f"  *** LOOKS LIKE AIRPODS (starts with 07) ***")
            
            print(f"  Match Target? {device.address.upper() == target_mac.upper() if target_mac else 'No Target'}")
            
    scanner = BleakScanner(detection_callback=callback)
    await scanner.start()
    await asyncio.sleep(5.0)
    await scanner.stop()

if __name__ == "__main__":
    mac, line = get_target_mac()
    if mac:
        print(f"Found AirPods in bluetoothctl: {line}")
        asyncio.run(scan(mac))
    else:
        print("No AirPods found in bluetoothctl devices.")
