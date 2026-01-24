
import hid
import time
import sys

def probe_keychron():
    # Keychron Link VID/PID
    VID = 0x3434
    PID = 0xd030
    
    # Looking for Interface 3 (Raw HID)
    target_interface = 3
    
    device_info = None
    devices = hid.enumerate(VID, PID)
    for d in devices:
        if d['interface_number'] == target_interface:
            device_info = d
            break
    
    if not device_info:
        print(f"Could not find Interface {target_interface} for Keychron device.")
        return

    try:
        print(f"Opening {device_info['product_string']} at {device_info['path']}...")
        h = hid.device()
        h.open_path(device_info['path'])
        
        # QMK Raw HID uses 32-byte packets
        # Common Keychron/VIA commands
        commands = [
            ("VIA Get Protocol", [0x01]),
            ("VIA Get Battery", [0x07]),
            ("VIA Get Battery (v2?)", [0x11]),
            ("Vendor Specific 1 (FE 01)", [0xFE, 0x01]),
            ("Vendor Specific 2 (FE 02)", [0xFE, 0x02]),
            ("Vendor Specific 3 (FE 81)", [0xFE, 0x81]),
            ("Vendor Specific 4 (02 07)", [0x02, 0x07]),
            ("VIA Get Device Info", [0x02]), # Some models use this
        ]
        
        for name, cmd in commands:
            packet = [0] * 32
            for i, val in enumerate(cmd):
                packet[i] = val
                
            print(f"Testing {name}: {cmd}")
            h.write(bytes(packet))
            
            # Non-blocking read with timeout
            start_time = time.time()
            found = False
            while time.time() - start_time < 0.3:
                res = h.read(64)
                if res:
                    # Filter out purely zero responses if possible, but keep them for debug
                    if any(res):
                         print(f"  Received: {' '.join([f'{b:02X}' for b in res])}")
                         found = True
                         break
                    else:
                         # Still found but all zeros
                         pass
            if not found:
                print("  No meaningful response.")
            print("-" * 10)
                
        h.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    probe_keychron()
