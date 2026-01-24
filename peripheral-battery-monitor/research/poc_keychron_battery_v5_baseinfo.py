
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

    # Try all interfaces
    # The launcher usually uses one that supports 64-byte reports.
    for device_info in devices:
        path = device_info['path']
        iface = device_info['interface_number']
        print(f"--- Probing Interface {iface} at {path} ---")
        
        try:
            h = hid.device()
            h.open_path(path)
            h.set_nonblocking(True)
            
            # Command: [ReportID, 0x00, 0x81, 0x01]
            # Standard QMK/Keychron report size is 32 or 64.
            # Let's try 64 first (Prepending Report ID 0x01)
            cmd = [0x01, 0x00, 0x81, 0x01]
            packet = cmd + [0] * (64 - len(cmd))
            
            # h.write() in hidapi: first byte is Report ID.
            print(f"Sending GetBaseInfo: {[hex(b) for b in cmd]}")
            h.write(bytes(packet))
            
            # Timeout loop
            start_time = time.time()
            found = False
            while time.time() - start_time < 0.5:
                res = h.read(64)
                if res:
                    if any(res):
                        print(f"  Received response ({len(res)} bytes):")
                        print(f"  {' '.join([f'{b:02X}' for b in res])}")
                        
                        # Parsing based on browser agent info:
                        # byte[11] is battery (0-100)
                        # byte[10] is charging?
                        if len(res) >= 12 and res[0] == 0x01 and res[3] == 0x01:
                            level = res[11]
                            charging = res[10]
                            print(f"  >>> SUCCESS! Battery Level: {level}% Charging: {bool(charging)}")
                            found = True
                            break
                        else:
                             print("  (Response format Mismatch)")
                time.sleep(0.02)
            
            if not found:
                print("  No match.")
                
            h.close()
        except Exception as e:
            print(f"  Error: {e}")
        print()

if __name__ == "__main__":
    probe_keychron()
