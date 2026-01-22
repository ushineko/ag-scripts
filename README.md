# AG Scripts

This repository contains various utility scripts for system management and automation.

## Scripts

| Script | Description |
| :--- | :--- |
| `docker-setup/setup_docker.sh` | Sets up Docker for the current user. Installs Docker if missing, enables the service, adds the user to the `docker` group, and verifies the installation with a test container. |
| `fix_readonly_mounts.py` | Scans for read-only mounts (specifically labeled "DataN" or "System"), attempts to fix them using `ntfsfix`, and verifies write access. Must be run as root. |
| `generate_data_mounts.py` | Generates `/etc/fstab` entries for block devices with labels matching "DataN" or "System", setting up mounts with appropriate permissions (uid/gid) for the current user. |
| `set-rgb/change_color.py` | Controls RGB lighting on various hardware devices (via OpenRGB, liquidctl, and ckb-next). Supports basic colors (red, green, blue, white, off). |
| `fake-screensaver/blank.html` | A simple black HTML page that acts as a screensaver. Hides the cursor and supports toggling full-screen mode by clicking or pressing Space. |

## Usage

Refer to individual scripts for specific usage instructions. Most Python scripts use `argparse` and support `-h/--help`.
