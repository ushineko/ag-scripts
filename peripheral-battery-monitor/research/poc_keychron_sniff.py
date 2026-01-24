
import hid
import time
import sys
import threading

def sniff_device(path, duration=3):
    try:
        h = hid.device()
        h.open_path(path)
        h.set_nonblocking(True)
        print(f"Sniffing {path} for {duration}s...")
        stop_time = time.time() + duration
        while time.time() < stop_time:
            res = h.read(64)
            if res:
                if any(res):
                    print(f"[{path}] Data: {' '.join([f'{b:02X}' for b in res])}")
            time.sleep(0.01)
        h.close()
    except Exception as e:
        print(f"[{path}] Error: {e}")

def main():
    VID = 0x3434
    PID = 0xd030
    devices = hid.enumerate(VID, PID)
    if not devices:
        print("No Keychron device found.")
        return
        
    # Get unique paths
    paths = list(set([d['path'] for d in devices]))
    print(f"Found {len(paths)} unique hidraw paths.")
    
    threads = []
    for p in paths:
        t = threading.Thread(target=sniff_device, args=(p,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()

if __name__ == "__main__":
    main()
