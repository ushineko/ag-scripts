
import hid

def enumerate_hid():
    print("Enumerating HID devices...")
    for device in hid.enumerate():
        # Keychron VID is 0x3434
        if device['vendor_id'] == 0x3434:
            print(f"Device: {device['product_string']}")
            print(f"  VID: {device['vendor_id']:04x}, PID: {device['product_id']:04x}")
            print(f"  Path: {device['path']}")
            print(f"  Interface: {device['interface_number']}")
            print(f"  Usage Page: {device['usage_page']:04x}")
            print(f"  Usage: {device['usage']:04x}")
            print("-" * 20)

if __name__ == "__main__":
    try:
        enumerate_hid()
    except ImportError:
        print("Error: 'hid' module not found. Try 'pip install hidapi'")
    except Exception as e:
        print(f"Error: {e}")
