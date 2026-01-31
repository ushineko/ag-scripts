# Miscellaneous System Utilities

QOL scripts created during a transition from Windows to Linux (CachyOS). These provide wrappers or functionality for various tasks that weren't immediately available out of the box—particularly around dealing with existing NTFS data drives and mount management.

## Table of Contents
- [Scripts](#scripts)
- [Installation](#installation)
- [Changelog](#changelog)

## Scripts

### fix_readonly_mounts.py

Automatically detects and repairs NTFS mounts that have fallen into read-only mode (common after improper shutdowns or dual-boot scenarios with Windows).

**Features:**
- Scans `/mnt/Data*` and `/mnt/System*` mount points
- Detects read-only mounts via `findmnt`
- Runs `ntfsfix -d` to clear dirty flags
- Remounts and verifies write access

**Usage:**
```bash
sudo python3 fix_readonly_mounts.py
```

**Requirements:**
- Root privileges
- `ntfs-3g` package (provides `ntfsfix`)
- `findmnt` (usually pre-installed)

---

### generate_data_mounts.py

Generates fstab entries for data drives labeled `DataN` (e.g., Data1, Data2) or `System`, with appropriate mount options for gaming (Steam/Proton compatibility).

**Features:**
- Scans block devices via `lsblk`
- Filters by label pattern (`Data\d+` or `System`)
- Skips removable and USB devices
- Generates fstab lines with proper uid/gid/umask for NTFS/exFAT

**Usage:**
```bash
python3 generate_data_mounts.py
# Output can be appended to /etc/fstab after review
```

**Output example:**
```
UUID=ABC123... /mnt/Data1 ntfs defaults,nofail,rw,exec,uid=1000,gid=1000,umask=000 0 2
```

---

### capture_window_screenshot.sh

Captures a screenshot of a specific window for README documentation. Uses kdotool for window management and spectacle for screenshots on KDE Wayland.

**Features:**
- Finds windows by class name or title (case-insensitive)
- Brings window to front before capturing
- Optional auto-launch if app not running
- Configurable delay for window settling
- Wayland-compatible

**Usage:**
```bash
# Screenshot a running app
./capture_window_screenshot.sh "peripheral-battery-monitor" assets/screenshot.png

# Launch if not running, then screenshot
./capture_window_screenshot.sh "Battery Monitor" screenshot.png --launch "python3 app.py" --delay 2
```

**Requirements:**
- `kdotool` (KDE window management)
- `spectacle` (KDE screenshot tool)

---

## Installation

These are standalone scripts with no installation required. Copy to a directory in your PATH or run directly.

## Changelog

### v1.1.0
- Added `capture_window_screenshot.sh`: Window screenshot utility for documentation

### v1.0.0
- Initial release
- `fix_readonly_mounts.py`: NTFS read-only mount detection and repair
- `generate_data_mounts.py`: fstab entry generation for data drives
