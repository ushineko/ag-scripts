
import hid
import time
import sys

def probe_keychron():
    # Keychron Link VID/PID
    VID = 0x3434
    PID = 0xd030
    
    # We are looking for Interface 3 (Raw HID)
    target_interface = 3
    
    device_path = None
    for d in hid.enumerate(VID, PID):
        if d['interface_number'] == target_interface:
            device_path = d['path']
            break
    
    if not device_path:
        print(f"Could not find Interface {target_interface} for Keychron device.")
        return

    try:
        h = hid.device()
        h.open_path(device_path)
        h.set_nonblocking(True)
        
        # Test commands:
        # 1. 0x01 (VIA Get Protocol)
        # 2. 0x07 (VIA Get Battery)
        # 3. 0xFE 0x01 (Custom Keychron Battery?)
        # 4. 0xFE 0x02 (Another custom?)
        
        commands = [
            [0x01],       # VIA Get Protocol
            [0x07],       # General Get Battery
            [0xFE, 0x01], # Keychron specific?
            [0xFE, 0x02]
        ]
        
        for cmd in commands:
            # HID reports are usually fixed length (32 or 64)
            # Prep packet
            packet = [0] * 32
            for i, val in enumerate(cmd):
                packet[i] = val
                
            print(f"Sending command: {cmd}")
            h.write(bytes(packet))
            
            # Wait for response
            time.sleep(0.1)
            res = h.read(64)
            if res:
                print(f"  Response: {list(res)}")
            else:
                print("  No response.")
                
        h.close()
    except Exception as e:
        print(f"Error opening device: {e}")

if __name__ == "__main__":
    probe_keychron()
