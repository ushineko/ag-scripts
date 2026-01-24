
import hid
import time

def find_battery_capable_devices():
    print("Searching for battery-capable HID devices...")
    devices = hid.enumerate()
    for d in devices:
        # Filter for Keychron (0x3434) or other common peripherals
        is_keychron = d['vendor_id'] == 0x3434
        
        # Open device to get more info
        try:
            h = hid.device()
            h.open_path(d['path'])
            
            # Print basic info
            name = d['product_string'] or "Unknown"
            print(f"Device: {name} (VID:{d['vendor_id']:04x} PID:{d['product_id']:04x})")
            print(f"  Path: {d['path']}")
            print(f"  Interface: {d['interface_number']}")
            print(f"  Usage Page: {d['usage_page']:04x}, Usage: {d['usage']:04x}")
            
            # Try to read some common battery-related feature reports
            # Some devices use specific report IDs for battery
            for rid in [0x01, 0x07, 0x08, 0xFE]:
                try:
                    res = h.get_feature_report(rid, 65)
                    if res:
                        print(f"  Feature Report {rid:02x}: {' '.join([f'{b:02x}' for b in res])}")
                except:
                    pass
            h.close()
            print("-" * 20)
        except Exception as e:
            # print(f"  Error accessing device {d['path']}: {e}")
            pass

if __name__ == "__main__":
    find_battery_capable_devices()
