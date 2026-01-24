
import hid
import time
import sys
import threading

def probe_path(path, name="Device"):
    try:
        h = hid.device()
        h.open_path(path)
        h.set_nonblocking(True)
        
        commands = [
            ("VIA Get Protocol", [0x01]),
            ("VIA Get Battery", [0x07]),
            ("Vendor Specific (02 07)", [0x02, 0x07]),
            ("Keychron Spec (FE 01)", [0xFE, 0x01]),
            ("Keychron Spec (07 01)", [0x07, 0x01]),
        ]
        
        for cmd_name, cmd in commands:
            packet = [0] * 32
            for i, val in enumerate(cmd):
                packet[i] = val
            
            # print(f"[{path}] Sending {cmd_name}...")
            h.write(bytes(packet))
            
            start_time = time.time()
            while time.time() - start_time < 0.1:
                res = h.read(64)
                if res:
                    if any(res):
                        print(f"[{path}] {cmd_name} Response: {' '.join([f'{b:02X}' for b in res])}")
                        break
                time.sleep(0.01)
        h.close()
    except Exception as e:
        # print(f"[{path}] Error: {e}")
        pass

def main():
    VID = 0x3434
    PID = 0xd030
    devices = hid.enumerate(VID, PID)
    if not devices:
        print("No Keychron device found.")
        return
        
    paths = list(set([d['path'] for d in devices]))
    print(f"Probing {len(paths)} paths...")
    
    for p in paths:
        probe_path(p)

if __name__ == "__main__":
    main()
