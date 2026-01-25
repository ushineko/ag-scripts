
import asyncio
from bleak import BleakScanner

def decode_airpods_data(hex_data):
    # Hex string to bytes
    data = bytes.fromhex(hex_data)
    
    # Check for Type 0x07
    if data[0] != 0x07:
        return None
        
    print(f"Analyzing Packet: {hex_data}")
    # Common layouts suggests:
    # Byte 6: Battery details? 
    # Some older docs says:
    # Byte 0: Length? (No, 0 is Type usually in ManData)
    # Actually ManData[0] is Type.
    
    # One known layout (AirPods Gen 1/2?):
    # Charge Info is around index 12-13?
    # Or nibbles?
    
    # Let's print candidate integers to spot values ~50-100
    candidates = []
    for i in range(len(data)):
        b = data[i]
        # raw value
        candidates.append(f"[{i}]:{b}")
        
        # Nibbles
        high = b >> 4
        low = b & 0x0F
        candidates.append(f"[{i}H]:{high}")
        candidates.append(f"[{i}L]:{low}")
        
    print("  " + ", ".join(candidates))
    return data

async def main():
    print("Scanning for Apple devices (0x004c) with Type 0x07...")
    
    def detection_callback(device, advertisement_data):
        if 76 in advertisement_data.manufacturer_data:
            data = advertisement_data.manufacturer_data[76]
            if len(data) > 0 and data[0] == 0x07:
                print(f"\nDevice: {device.address} (RSSI: {advertisement_data.rssi})")
                decode_airpods_data(data.hex())

    scanner = BleakScanner(detection_callback=detection_callback)
    await scanner.start()
    await asyncio.sleep(5.0)
    await scanner.stop()

if __name__ == "__main__":
    asyncio.run(main())
