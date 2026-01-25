
import asyncio
from bleak import BleakScanner

async def main():
    print("Scanning for Apple devices (Manufacturer ID 0x004c)...")
    
    def detection_callback(device, advertisement_data):
        # Apple Manufacturer ID is 76 (0x004c)
        if 76 in advertisement_data.manufacturer_data:
            data = advertisement_data.manufacturer_data[76]
            print(f"Device: {device.name} ({device.address})")
            print(f"  RSSI: {advertisement_data.rssi}")
            print(f"  Data (Hex): {data.hex()}")
            print("-" * 20)

    scanner = BleakScanner(detection_callback=detection_callback)
    await scanner.start()
    await asyncio.sleep(10.0)
    await scanner.stop()

if __name__ == "__main__":
    asyncio.run(main())
