#!/usr/bin/env python3
import subprocess
import sys
import os
import time
import shutil

# Target mount patterns (prefixes) to check
TARGET_MOUNTS = ["/mnt/Data", "/mnt/System"]

def log(msg, type="INFO"):
    colors = {
        "INFO": "\033[94m",    # Blue
        "SUCCESS": "\033[92m", # Green
        "WARNING": "\033[93m", # Yellow
        "ERROR": "\033[91m",   # Red
        "RESET": "\033[0m"
    }
    prefix = f"{colors.get(type, '')}[{type}]{colors['RESET']}"
    print(f"{prefix} {msg}")

def check_dependencies():
    """Ensure ntfsfix is installed."""
    if not shutil.which("ntfsfix"):
        log("Error: 'ntfsfix' utility not found. Please install ntfs-3g package.", "ERROR")
        sys.exit(1)
    if not shutil.which("findmnt"):
        log("Error: 'findmnt' utility not found.", "ERROR")
        sys.exit(1)

def get_target_mounts():
    """Find all relevant mounts and their status."""
    mounts = []
    try:
        # List all mounts in JSON format
        cmd = ["findmnt", "-J", "-o", "TARGET,SOURCE,OPTIONS,FSTYPE"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        import json
        data = json.loads(result.stdout)
        
        filesystems = data.get("filesystems", [])
        
        # findmnt json output can be a list or a dictionary depending on version/structure
        # Flatten if necessary (though top level usually has 'filesystems' list)
        
        def filter_mounts(fs_list):
            matches = []
            for fs in fs_list:
                target = fs.get("target", "")
                # Check if it matches our target prefixes
                if any(target.startswith(t) for t in TARGET_MOUNTS):
                    matches.append(fs)
                
                # Recurse if children exist
                if "children" in fs:
                    matches.extend(filter_mounts(fs["children"]))
            return matches

        return filter_mounts(filesystems)

    except Exception as e:
        log(f"Failed to query mounts: {e}", "ERROR")
        sys.exit(1)

def fix_mount(mount_point, device):
    """Unmount, ntfsfix, and remount a specific device."""
    log(f"Attempting to fix {mount_point} ({device})...", "WARNING")
    
    # 1. Unmount
    log(f"Unmounting {mount_point}...", "INFO")
    try:
        subprocess.run(["umount", mount_point], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        log(f"Unmount failed: {e.stderr.decode().strip()}", "ERROR")
        # Try lazy unmount if standard failed (e.g. device busy)
        log("Attempting lazy unmount...", "WARNING")
        try:
            subprocess.run(["umount", "-l", mount_point], check=True)
        except subprocess.CalledProcessError as e2:
             log(f"Lazy unmount also failed: {e2}", "ERROR")
             return False

    # 2. Run ntfsfix
    log(f"Running ntfsfix on {device}...", "INFO")
    try:
        # -d: Clear the dirty flag
        # -b: Clear the bad sector list (optional, but often helpful for dirty flags)
        cmd = ["ntfsfix", "-d", device]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log(f"ntfsfix failed: {result.stderr.strip()}", "ERROR")
            # If it failed, we should probably stop and not try to remount blindly, 
            # OR try to remount anyway to restore access? 
            # Usually better to try remounting so the user isn't left with nothing.
            log("Attempting to remount anyway to restore access...", "WARNING")
        else:
            log(f"ntfsfix output:\n{result.stdout.strip()}", "SUCCESS")
    except FileNotFoundError:
        log("ntfsfix command not found!", "ERROR")
        return False

    # 3. Remount
    log(f"Remounting {mount_point}...", "INFO")
    try:
        subprocess.run(["mount", mount_point], check=True)
        log(f"Remounted {mount_point}.", "SUCCESS")
    except subprocess.CalledProcessError as e:
        log(f"Remount failed: {e}", "ERROR")
        return False
        
    return True

def verify_write_access(mount_point):
    """Check if we can write a file to the mount point."""
    test_file = os.path.join(mount_point, ".rw_test_" + str(int(time.time())))
    try:
        with open(test_file, 'w') as f:
            f.write("Write test success")
        os.remove(test_file)
        return True
    except OSError as e:
        log(f"Write test failed on {mount_point}: {e}", "ERROR")
        return False

def main():
    if os.geteuid() != 0:
        log("This script must be run as root (sudo).", "ERROR")
        sys.exit(1)

    check_dependencies()
    
    log("Scanning for relevant mounts...", "INFO")
    mounts = get_target_mounts()
    
    if not mounts:
        log("No mounts found matching target patterns.", "WARNING")
        return

    fixed_count = 0
    skipped_count = 0
    error_count = 0

    for m in mounts:
        target = m['target']
        options = m['options']
        device = m['source']
        
        log(f"Checking {target}...", "INFO")
        
        is_ro = "ro" in options.split(",")
        
        if is_ro:
            log(f"FOUND READ-ONLY MOUNT: {target}", "WARNING")
            if fix_mount(target, device):
                # Verify
                if verify_write_access(target):
                    log(f"Verification SUCCESS: {target} is now writable.", "SUCCESS")
                    fixed_count += 1
                else:
                    log(f"Verification FAILED: {target} is still read-only.", "ERROR")
                    error_count += 1
            else:
                error_count += 1
        else:
            # log(f"{target} is already read-write (r/w). Skipping.", "INFO") 
            # Too verbose? No, user asked for verbose.
            # But let's actually double check with a write test just to be sure
            if verify_write_access(target):
                log(f"{target} is healthy (RW).", "SUCCESS")
                skipped_count += 1
            else:
                 log(f"{target} reports RW but write test FAILED! Attempting fix...", "WARNING")
                 if fix_mount(target, device):
                     if verify_write_access(target):
                        fixed_count += 1
                     else:
                        error_count += 1

    log("-------------------------", "INFO")
    log(f"Summary: {fixed_count} Fixed, {skipped_count} OK, {error_count} Failed.", "INFO")

if __name__ == "__main__":
    main()
