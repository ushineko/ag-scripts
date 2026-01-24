
import hid
import time

def test_iface1():
    # Keychron Link (2.4G) VID:PID
    VID = 0x3434
    PID = 0xd030
    
    # We want to find the specific path for Interface 1
    # Usage Page for Vendor Specific (Keychron often uses FF60 or similar for comms)
    devices = hid.enumerate(VID, PID)
    target_path = None
    
    print(f"Found {len(devices)} Keychron Link interfaces:")
    for d in devices:
        print(f"Iface {d['interface_number']} - Path: {d['path']} - Page: {d['usage_page']:04X}")
        if d['interface_number'] == 1:
            target_path = d['path']

    if not target_path:
        print("Could not find Interface 1")
        return

    try:
        h = hid.device()
        h.open_path(target_path)
        h.set_nonblocking(True)
        print(f"Opened {target_path}")

        # Command to get base info (includes battery at index 11)
        # Packet: [ReportID, 0, 0x81, 1, ...0]
        # Trying both Report ID 0 (raw) and 1
        for rid in [0, 1]:
            cmd = [rid, 0x00, 0x81, 0x01]
            cmd += [0] * (64 - len(cmd))
            print(f"Writing probe (RID {rid})...")
            h.write(bytes(cmd))
            time.sleep(0.1)
            res = h.read(64)
            if res:
                print(f"Response: {' '.join([f'{b:02X}' for b in res])}")
            else:
                print("No response")

        h.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_iface1()
