#!/usr/bin/env python3
import subprocess
import json
import re
import sys

def get_block_devices():
    try:
        # Run lsblk to get JSON output with specific columns
        # Added MOUNTPOINT to see if it's already mounted
        # Added RM to check if device is removable
        # Added TRAN to check transport type (e.g. usb)
        result = subprocess.run(
            ['lsblk', '-J', '-o', 'NAME,LABEL,UUID,FSTYPE,MOUNTPOINT,RM,TRAN'],
            capture_output=True,
            text=True,
            check=True
        )
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error running lsblk: {e}", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"Error parsing lsblk output: {e}", file=sys.stderr)
        return None

import pwd

def get_user_ids(username):
    try:
        pw = pwd.getpwnam(username)
        return pw.pw_uid, pw.pw_gid
    except KeyError:
        print(f"User '{username}' not found.", file=sys.stderr)
        return None, None

def generate_fstab_entries(data, uid, gid):
    if not data or 'blockdevices' not in data:
        return

    # Regular expression to match "DataN" (where N is a number) OR "System"
    label_pattern = re.compile(r'^(Data\d+|System)$')
    
    entries = []
    
    # Filesystems that support uid/gid options for ownership mapping
    # ext4/xfs usually use filesystem-level permissions, but ntfs/vfat need mount options.
    # We will apply it to ntfs, vfat, exfa, fuseblk (often ntfs).
    ownership_fs = {'ntfs', 'vfat', 'exfat', 'fuseblk'}

    def traverse_devices(devices, parent_tran=None):
        for device in devices:
            label = device.get('label')
            
            # Determine transport: use device's own tran if present, else inherit from parent
            tran = device.get('tran')
            if not tran:
                tran = parent_tran
                
            # Check if device is removable (lsblk returns boolean or "1"/"0")
            is_removable = device.get('rm')
            
            # Filter conditions:
            # 1. Removable flag is set
            if is_removable == True or is_removable == '1' or is_removable == 'true':
                 pass # Skip
            # 2. Transport is USB
            elif tran == 'usb':
                 pass # Skip
            elif label and label_pattern.match(label):
                uuid = device.get('uuid')
                fstype = device.get('fstype')
                current_mount = device.get('mountpoint')
                
                if uuid and fstype:
                    mount_point = f"/mnt/{label}"
                    
                    # Base options
                    # defaults: rw, suid, dev, exec, auto, nouser, async
                    # nofail: don't block boot if missing
                    options = "defaults,nofail,rw,exec"
                    
                    # Add ownership options if filesystem supports it and we have a valid uid/gid
                    if fstype in ownership_fs and uid is not None and gid is not None:
                        # For gaming (Steam/Proton), we want full permissions.
                        # uid/gid: Set owner to user
                        # umask=000: Allow rwx for user/group/others (avoids some Proton permission issues)
                        # windows_names: (ntfs-3g specific but harmless on some) - prevents using names invalid in windows
                        options += f",uid={uid},gid={gid},umask=000"
                        
                    # fstab format: UUID=<uuid> <mount_point> <fstype> <options> <dump> <pass>
                    entry = f"UUID={uuid} {mount_point} {fstype} {options} 0 2"
                    
                    if current_mount:
                        entry += f" # Currently mounted at: {current_mount}"
                    
                    entries.append(entry)
            
            # Recurse into children if they exist, passing down the current effective tran
            if 'children' in device:
                traverse_devices(device['children'], parent_tran=tran)

    traverse_devices(data['blockdevices'])
    
    return entries

def main():
    target_user = 'nverenin'
    uid, gid = get_user_ids(target_user)
    
    if uid is None:
        print(f"Warning: Could not determine UID/GID for {target_user}. Generated mounts might have permission issues.", file=sys.stderr)

    data = get_block_devices()
    if data:
        entries = generate_fstab_entries(data, uid, gid)
        if entries:
            for entry in entries:
                print(entry)
        else:
            # It's okay to output nothing if no devices match, but maybe a message to stderr helps debugging
            print("No devices matching pattern 'DataN' or 'System' found.", file=sys.stderr)

if __name__ == '__main__':
    main()
