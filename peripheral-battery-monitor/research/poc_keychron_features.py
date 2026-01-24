
import hid
import time
import sys

def probe_feature_reports(path):
    try:
        h = hid.device()
        h.open_path(path)
        print(f"--- Probing Feature Reports for {path} ---")
        
        for rid in range(0, 256):
            try:
                # Try reading feature report rid
                # hidapi get_feature_report prepends byte 0 with RID
                res = h.get_feature_report(rid, 65)
                if res and any(res):
                    print(f"  RID {rid:02X} Feature: {' '.join([f'{b:02X}' for b in res])}")
            except:
                pass
        h.close()
    except Exception as e:
        print(f"  Error opening {path}: {e}")

def main():
    VID = 0x3434
    PID = 0xd030
    devices = hid.enumerate(VID, PID)
    if not devices:
        print("No Keychron device found.")
        return
        
    paths = list(set([d['path'] for d in devices]))
    for p in paths:
        probe_feature_reports(p)

if __name__ == "__main__":
    main()
