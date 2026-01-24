
import hid
import time
import sys
import threading

# Potential battery commands for Keychron HE / QMK / VIA
COMMANDS = [
    ("VIA Get Protocol", [0x01]),
    ("VIA Get Battery", [0x07]),
    ("Keychron Base Info", [0x01, 0x00, 0x81, 0x01]),
    ("Keychron Battery Vendor", [0xFE, 0x01]),
    ("Keychron Battery Vendor 2", [0x02, 0x07]),
]

def sniff_and_test(device_info):
    path = device_info['path']
    iface = device_info['interface_number']
    up = device_info['usage_page']
    u = device_info['usage']
    
    try:
        h = hid.device()
        h.open_path(path)
        h.set_nonblocking(True)
        print(f"[*] Started probing Interface {iface} (Usage Page: {up:04X}, Usage: {u:04X}) at {path}")
        
        # 1. Test Active Commands
        for name, cmd in COMMANDS:
            # Try both raw (ID 0) and ID 1
            for rid in [0, 1]:
                packet = [rid] + cmd
                packet += [0] * (64 - len(packet))
                try:
                    h.write(bytes(packet))
                    time.sleep(0.05)
                    res = h.read(64)
                    if res and any(res):
                        print(f"[!] {path} responded to {name} (RID {rid}): {' '.join([f'{b:02X}' for b in res])}")
                except:
                    pass
        
        # 2. Passive Sniffing (Wait for user action)
        print(f"[*] Sniffing {path} for 10 seconds. PLEASE PRESS Fn+B NOW...")
        stop_time = time.time() + 10
        while time.time() < stop_time:
            res = h.read(64)
            if res and any(res):
                print(f"[DATA] {path} (Iface {iface}): {' '.join([f'{b:02X}' for b in res])}")
                # Analyze common offsets
                # If byte 0 is 0x01 and byte 3 is 0x01 -> maybe the BaseInfo response
                if len(res) > 11 and res[0] == 0x01:
                    print(f"  Plausible Battery at index 11: {res[11]}%")
            time.sleep(0.01)
            
        h.close()
    except Exception as e:
        print(f"[ERROR] {path}: {e}")

def main():
    VID = 0x3434
    PID = 0xd030
    devices = hid.enumerate(VID, PID)
    if not devices:
        print("No Keychron device found.")
        return
        
    print(f"Found {len(devices)} Keychron HID interfaces. Starting multi-threaded probe...")
    
    threads = []
    # Use unique paths to avoid double opening the same hidraw (though hidapi handles it)
    paths = {}
    for d in devices:
        if d['path'] not in paths:
             paths[d['path']] = d
             
    for p, d in paths.items():
        t = threading.Thread(target=sniff_and_test, args=(d,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()

if __name__ == "__main__":
    main()
