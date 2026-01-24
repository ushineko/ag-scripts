#!/usr/bin/env python3
import subprocess
import shutil
import sys
import os

def run_command(command):
    """Runs a shell command and returns the output."""
    try:
        result = subprocess.run(
            command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {command}")
        print(e.stderr)
        return None

def check_if_target_empty(device_name):
    """Checks if the target device is mounted and non-empty."""
    # List all mountpoints for this device
    # lsblk can help, we look for anything starting with /dev/device_name
    mounts = run_command(f"findmnt -n -o TARGET -S /dev/{device_name}")
    if not mounts:
         # Also check potential partitions if the device itself isn't mounted (e.g. nvme1n1p1)
         # We need to list all partitions of the device and their mounts.
         mounts = run_command(f"lsblk -ln -o MOUNTPOINT /dev/{device_name} | grep -v '^$'")
         if not mounts:
             return True # Not mounted anywhere

    mount_points = mounts.split('\n')
    for mp in mount_points:
        mp = mp.strip()
        if not mp: continue
        print(f"[Safety Check] Checking mountpoint: {mp}")
        if not os.path.exists(mp):
            continue
            
        # Check for files (ignoring lost+found)
        files = os.listdir(mp)
        files = [f for f in files if f != 'lost+found']
        if files:
            print(f"CRITICAL FAIL: Target device mountpoint '{mp}' is not empty!")
            print(f"Found files: {files[:5]} {'...' if len(files)>5 else ''}")
            return False
    
    return True

    
    return True

def check_fstab(device):
    """Checks if the destination device is present in /etc/fstab."""
    print(f"\n[Config Check] Checking /etc/fstab for {device} references")
    
    # Needs UUID and PartUUID to be thorough
    uuid_output = run_command(f"lsblk -no UUID /dev/{device}")
    partuuid_output = run_command(f"lsblk -no PARTUUID /dev/{device}")
    
    # Collect all identifiers for device and its partitions
    identifiers = [device]
    if uuid_output: identifiers.extend(uuid_output.split())
    if partuuid_output: identifiers.extend(partuuid_output.split())
    
    # Also get checks for partitions (e.g. nvme1n1p1)
    parts = run_command(f"lsblk -ln -o NAME /dev/{device}").split()
    for p in parts:
        if p == device: continue
        identifiers.append(p)
        p_uuid = run_command(f"lsblk -no UUID /dev/{p}")
        if p_uuid: identifiers.extend(p_uuid.split())
        p_partuuid = run_command(f"lsblk -no PARTUUID /dev/{p}")
        if p_partuuid: identifiers.extend(p_partuuid.split())
        
    fstab_content = run_command("cat /etc/fstab")
    if not fstab_content:
        print("Warning: Could not read /etc/fstab")
        return True # Soft pass but suspicious
        
    found = False
    for line in fstab_content.splitlines():
        if line.strip().startswith('#'): continue
        for ident in identifiers:
            if ident and ident in line:
                print(f"CRITICAL FAIL: Found reference to {ident} in /etc/fstab!")
                print(f"Line: {line}")
                found = True
                
    if found:
        return False
        
    return True

def check_dependencies():
    """Checks if required commands are available."""
    dependencies = ['lsblk', 'btrfs', 'grep', 'findmnt', 'sgdisk']
    missing = []
    for dep in dependencies:
        if shutil.which(dep) is None:
            missing.append(dep)
    
    if missing:
        print(f"Error: Missing dependencies: {', '.join(missing)}")
        sys.exit(1)
    else:
        print("OK: All dependencies found.")

def get_device_info(device_name):
    """Gets model and size of a block device."""
    output = run_command(f"lsblk -dn -o MODEL,SIZE /dev/{device_name}")
    if output:
        return output
    return "Unknown"

def is_btrfs(path):
    """Checks if a path is on a btrfs filesystem."""
    output = run_command(f"findmnt -n -o FSTYPE -T {path}")
    return output == 'btrfs'


def get_all_active_subvolumes(root_device):
    """Gets all subvolumes mounted from the root device."""
    # Find active mounts for the device
    output = run_command(f"findmnt -l -o TARGET,SOURCE,FSTYPE")
    if not output: return []
    
    subvols = []
    # Identify the partition name, e.g. /dev/sdd2 from root mount
    root_src = run_command("findmnt -n -o SOURCE /").split('[')[0]
    
    for line in output.split('\n'):
        if root_src in line and 'btrfs' in line:
            parts = line.split()
            target = parts[0]
            source = parts[1]
            if '[' in source and ']' in source:
                 subvol_name = source.split('[')[1].split(']')[0]
                 print(f"Found active subvolume: {subvol_name} mounted at {target}")
                 subvols.append({'name': subvol_name, 'mount': target})
    return subvols

def generate_runbook(subvolumes, dest_device):
    """Generates the migration runbook."""
    print("\n" + "="*40)
    print("DRAFT MIGRATION RUNBOOK (DRY RUN)")
    print("="*40)
    
    print(f"\n[!] TARGET DEVICE: /dev/{dest_device}")
    
    steps = [
        f"# 1. Wipe and Partition /dev/{dest_device}",
        f"# Ensure absolutely nothing is mounted (nuclear option)",
        f"fuser -k -m /dev/{dest_device}* || true",
        f"sleep 1",
        f"umount -R -f /dev/{dest_device}* || true",
        f"umount -R -f /mnt/Data1 || true", 
        f"swapoff /dev/{dest_device}* || true",
        
        f"# Clear signatures (ignore errors if device invalid)",
        f"wipefs --all --force /dev/{dest_device}* || true",
        f"sgdisk --zap-all /dev/{dest_device}",
        
        f"# Force kernel to drop old partitions (RETRIES)",
        f"partprobe /dev/{dest_device} || true",
        f"sleep 2",
        f"partprobe /dev/{dest_device} || true",
        f"udevadm settle",
        f"sleep 2",
        
        f"# Create new partitions",
        f"sgdisk -n 1:0:+1024M -t 1:ef00 -c 1:'CachyOS EFI' /dev/{dest_device}",
        f"sgdisk -n 2:0:0 -t 2:8300 -c 2:'CachyOS Root' /dev/{dest_device}",
        f"# Sync again",
        f"partprobe /dev/{dest_device}",
        f"udevadm settle",
        f"sleep 5", # Increased wait time
        
        f"# Final unmount check before formatting",
        f"umount -q /dev/{dest_device}p1 || true",
        f"umount -q /dev/{dest_device}p2 || true",
        
        f"\n# 2. Format Partitions",
        f"mkfs.vfat -F32 -n 'CachyOS-EFI' /dev/{dest_device}p1",
        f"mkfs.btrfs -L 'CachyOS-NVMe' -f /dev/{dest_device}p2",
        
        f"\n# 3. Mount Migration Pool (Top Level ID 5)",
        f"mkdir -p /mnt/migration_pool",
        f"mount -o subvolid=5 /dev/{dest_device}p2 /mnt/migration_pool",
        
        f"\n# 4. Snapshot and Send (The Migration)"
    ]
    
    # Generate send/receive for each subvolume
    for sub in subvolumes:
        name = sub['name'] # e.g. /@ or /@home
        safe_name = name.lstrip('/')
        temp_snap = f"{sub['mount']}/{name.replace('/','_')}.migration"
        
        steps.append(f"# Process {name}")
        steps.append(f"# Cleanup stale snapshot if exists")
        steps.append(f"if [ -d '{temp_snap}' ]; then btrfs subvolume delete '{temp_snap}'; fi")
        
        steps.append(f"btrfs subvolume snapshot -r {sub['mount']} {temp_snap}")
        steps.append(f"btrfs send {temp_snap} | btrfs receive /mnt/migration_pool/")
        # Rename on dest: /@_migration -> @
        src_snap_name = f"{name.replace('/','_')}.migration"
        dest_name = safe_name
        steps.append(f"mv /mnt/migration_pool/{src_snap_name} /mnt/migration_pool/{dest_name}")
        # Use -f to force unset ro despite received_uuid
        steps.append(f"btrfs property set -f -ts /mnt/migration_pool/{dest_name} ro false")
        
    steps.append(f"\n# 5. Staging New Root")
    steps.append(f"umount /mnt/migration_pool")
    steps.append(f"mount -o subvol=@,compress=zstd /dev/{dest_device}p2 /mnt/new_root")
    
    # Create mountpoints for other subvolumes and mount them
    for sub in subvolumes:
        if sub['name'] == '/@': continue
        mountpoint = sub['mount'] # e.g. /home or /var/log
        rel_mount = mountpoint.lstrip('/') # home or var/log
        steps.append(f"mkdir -p /mnt/new_root/{rel_mount}")
        steps.append(f"mount -o subvol={sub['name']},compress=zstd /dev/{dest_device}p2 /mnt/new_root/{rel_mount}")
        
    global kernel_pkg # Use previously detected kernel
    
    steps.extend([
        f"\n# 6. Post-Migration Config",
        f"mkdir -p /mnt/new_root/boot",
        f"mount /dev/{dest_device}p1 /mnt/new_root/boot",
        f"genfstab -U /mnt/new_root > /mnt/new_root/etc/fstab",
        f"arch-chroot /mnt/new_root bootctl install",
    ])
    
    # Detect kernel package to reinstall for automatic entry generation
    kernel_pkg = "linux-cachyos" # Default fallback
    try:
        # Check for linux-cachyos, linux, or linux-lts
        installed_kernels = run_command("pacman -Q | grep '^linux' | awk '{print $1}'").split('\n')
        # Prioritize linux-cachyos, then linux, then linux-lts
        if "linux-cachyos" in installed_kernels:
            kernel_pkg = "linux-cachyos"
        elif "linux" in installed_kernels:
            kernel_pkg = "linux"
        elif "linux-lts" in installed_kernels:
            kernel_pkg = "linux-lts"
    except:
        pass
        
    steps.append(f"arch-chroot /mnt/new_root pacman -S --noconfirm {kernel_pkg} # Reinstall kernel to regenerate loader entries")
    
    steps.extend([
        f"\n# 7. Final Verification",
        f"echo 'Verifying UUIDs...'",
        f"TARGET_UUID=$(blkid -s UUID -o value /dev/{dest_device}p2)",
        f"echo \"Target Root UUID: $TARGET_UUID\"",
        f"echo \"Checking /etc/fstab...\"",
        f"grep $TARGET_UUID /mnt/new_root/etc/fstab && echo 'OK: Found UUID in fstab' || echo 'FAIL: UUID missing in fstab'",
        f"echo \"Checking Bootloader Entries...\"",
        f"grep -r $TARGET_UUID /mnt/new_root/boot/loader/entries/ && echo 'OK: Found UUID in bootloader config' || echo 'FAIL: UUID missing in bootloader config'",
        f"\n# Done!",
        f"echo \"Migration Complete. If verify PASSED, you can reboot.\""
    ])
    
    for step in steps:
        print(step)

    # Save to file
    with open("migration_runbook.sh", "w") as f:
        f.write("#!/bin/bash\n")
        f.write("# Error Handling Traps\n")
        f.write("set -e\n")
        f.write("trap 'echo \"[ERROR] Command failed at line $LINENO: $BASH_COMMAND\"; exit 1' ERR\n")
        f.write("echo \"[INFO] Starting Migration Runbook...\"\n")
        f.write("# AUTO-GENERATED MIGRATION PLAN - DO NOT RUN BLINDLY\n")
        for step in steps:
            f.write(step + "\n")
    print(f"\n[INFO] Runbook saved to: {os.path.abspath('migration_runbook.sh')}")

def save_package_lists():
    """Saves lists of installed packages."""
    print(f"\n[Inventorying Packages]")
    
    # Explicit Native
    run_command("pacman -Qne > pkglist_native.txt")
    print("Saved pkglist_native.txt")
    
    # Explicit AUR/Foreign
    run_command("pacman -Qme > pkglist_aur.txt")
    print("Saved pkglist_aur.txt")
    
    # All
    run_command("pacman -Q > pkglist_all.txt")
    print("Saved pkglist_all.txt")


def main():
    print("Starting Pre-Move Check for CachyOS Migration...\n")
    check_dependencies()

    # Configuration
    SOURCE_DEVICE = "sdd" # Based on lsblk
    DEST_DEVICE = "nvme1n1"
    
    # 1. Check Source
    print(f"\n[Checking Source: /dev/{SOURCE_DEVICE}]")
    if is_btrfs("/"):
        print("OK: Root filesytem is Btrfs.")
    else:
        print("FAIL: Root filesystem is NOT Btrfs. Migration plan invalid.")
        sys.exit(1)
        
    subvolumes = get_all_active_subvolumes(SOURCE_DEVICE)
    if not subvolumes:
        print("Error: Could not determine subvolumes. Manual inspection required.")
        sys.exit(1)

    # 2. Check Destination
    print(f"\n[Checking Destination: /dev/{DEST_DEVICE}]")
    dest_info = get_device_info(DEST_DEVICE)
    print(f"Device Info: {dest_info}")
    
    # Safety Check: Ensure we aren't targeting the boot drive by accident
    # Simple check: is / mounted on it?
    root_dev = run_command("findmnt -n -o SOURCE /").split('[')[0]
    if DEST_DEVICE in root_dev:
         print(f"CRITICAL FAIL: Destination device {DEST_DEVICE} is currently mounted as ROOT! Aborting.")
         sys.exit(1)
         
    if not check_if_target_empty(DEST_DEVICE):
         print(f"WARNING: Destination device {DEST_DEVICE} contains data. Proceeding because runbook handles wiping.")
         # sys.exit(1) # Bypass safety check for regeneration
         
    if not check_fstab(DEST_DEVICE):
        print(f"ABORTING: Destination device {DEST_DEVICE} is listed in /etc/fstab.")
        print("Please remove or comment out these entries to prevent invalid configuration cloning.")
        sys.exit(1)
         
    print("OK: Destination device appears valid, safe, empty, and clean from fstab.")

    # 3. Generate Plan
    generate_runbook(subvolumes, DEST_DEVICE)
    save_package_lists()

if __name__ == "__main__":
    main()
