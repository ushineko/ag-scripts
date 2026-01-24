
import hid
import time
import sys

def probe_keychron():
    # Keychron Link VID/PID
    VID = 0x3434
    PID = 0xd030
    
    devices = hid.enumerate(VID, PID)
    if not devices:
        print("No Keychron device found.")
        return

    # Targeting Interface 3 (Raw HID)
    target_iface = 3
    path = None
    for d in devices:
        if d['interface_number'] == target_iface:
            path = d['path']
            break
            
    if not path:
        print(f"Could not find Interface {target_iface}")
        return

    try:
        h = hid.device()
        h.open_path(path)
        h.set_nonblocking(True)
        print(f"Probing {path} (Interface {target_iface})...")

        # Try common QMK/Keychron query commands
        # Format: (ReportID, [Bytes])
        # If ReportID is 0, we send [0x00, bytes...]
        queries = [
            (0, [0x01]),             # Get Protocol
            (0, [0x07]),             # Get Battery
            (0, [0xFE, 0x01]),       # Keychron Spec
            (0, [0x02, 0x07]),       # Get Battery v2
            (1, [0x01]),             # Standard Report 1
            (1, [0x00, 0x81, 0x01]), # GetBaseInfo (from Launcher)
            (1, [0x07, 0xFE]),       # Another common one
        ]

        for rid, data in queries:
            packet = [rid] + data
            packet += [0] * (32 - len(packet)) # 32 byte common for raw hid
            
            print(f"Testing RID={rid}, Data={data}")
            try:
                h.write(bytes(packet))
            except Exception as e:
                print(f"  Write Error: {e}")
                continue
                
            start_time = time.time()
            while time.time() - start_time < 0.15:
                res = h.read(64)
                if res and any(res):
                    print(f"  >>> Received: {' '.join([f'{b:02X}' for b in res])}")
                    break
                time.sleep(0.01)
        
        h.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    probe_keychron()
