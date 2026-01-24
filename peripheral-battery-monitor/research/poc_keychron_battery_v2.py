
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
    for d in hid.enumerate(VID, PID):
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
        commands = [
            # Standard VIA commands
            [0x01],       # Get Protocol
            [0x07],       # General Get Battery (VIA fork)
            [0x11],       # Another common battery command
            # Keychron Specific?
            [0xFE, 0x01], # Vendor specific 1
            [0xFE, 0x02], # Vendor specific 2
            [0xFE, 0x81], # Vendor specific 1 (alternate)
            [0x02, 0x07], # Another variant
        ]
        
        for cmd in commands:
            packet = [0] * 32
            for i, val in enumerate(cmd):
                packet[i] = val
                
            print(f"Sending: {hex(cmd[0])} {cmd[1:] if len(cmd) > 1 else ''}")
            h.write(bytes(packet))
            
            # Non-blocking read with timeout
            start_time = time.time()
            found = False
            while time.time() - start_time < 0.2:
                res = h.read(64)
                if res:
                    print(f"  Received: {list(res)}")
                    found = True
                    break
            if not found:
                print("  Timeout.")
                
        h.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    probe_keychron()
