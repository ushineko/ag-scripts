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
| `fake-screensaver/fake_screensaver.py` | A PyQt-based fake screensaver that keeps the mouse cursor visible. Includes a desktop entry. |
| `audio-source-switcher/audio_source_switcher.py` | A feature-rich "Audio Source Switcher" with priority auto-switching, **Microphone Association** (Auto/Manual linking), Bluetooth device management (auto-connect), JamesDSP integration (smart rewiring), Jack Detection, and Wayland-compatible global hotkeys. |
| `peripheral-battery-monitor/peripheral-battery.py` | A compact, always-on-top dashboard for Logitech mouse, Keychron K4 HE (Wired/Wireless/BT), Arctis headset, and AirPods battery monitoring (L/R/Case status via BLE). Optimized for KDE Wayland. |
| `the-great-cachyos-move/pre_move_check.py` | Migration toolkit for moving a running CachyOS (Btrfs) installation from one drive to another (e.g., SATA to NVMe) using `btrfs send/receive`. Includes pre-checks and runbook generation. |
| `qbittorrent-vpn-wrapper/qbittorrent_vpn_wrapper.py` | Secure wrapper for qBittorrent with VPN binding, IP geolocation check, idle auto-shutdown, and a persistent "glued" status dashboard. |
| `vpn-toggle/toggle_vpn.sh` | GUI-based script (kdialog/zenity) to toggle NetworkManager VPN connections, bounce them, or open settings. Ideal for hotkeys. |
| `alacritty-maximizer/main.py` | PyQt6 GUI (bundled with an installer/launcher) to launch Alacritty windows fully maximized on specific monitors without titlebars. Manages KWin rules automatically. |
| `kvm-setup/install.sh` | Setup scripts for KVM (QEMU/libvirt) on CachyOS. Configures libvirt group and permissions, and warns about VirtualBox coexistence. |
| `pinball-fx/configure_kwin.py` | "Window Fixer" utility for Pinball FX. Interactive menu to force the game onto any selected monitor and manage persistent KWin rules. |
| `plasmashell-restart/restart.sh` | Restarts or refreshes the KDE Plasma 6 shell via systemd (full restart) or D-Bus (light refresh). Keeps taskbar operative. |
| `claude-code-setup/install.sh` | Setup script for Claude Code CLI. Installs/Updates Node.js (via Conda if needed) and `@anthropic-ai/claude-code` globally. |

## Usage

Refer to individual scripts for specific usage instructions. Most Python scripts use `argparse` and support `-h/--help`.
