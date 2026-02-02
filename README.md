# AG Scripts

QOL scripts and utilities created during a transition from Windows to Linux (CachyOS). These provide wrappers or functionality for various tasks that weren't immediately available out of the box.

## Highlights

A couple of projects that may be of broader interest—either as standalone utilities or as code references/learning vehicles:

| Project | Description |
| :--- | :--- |
| [audio-source-switcher](audio-source-switcher/) | Feature-rich PyQt6 audio manager with priority auto-switching, mic association, Bluetooth device management, JamesDSP integration, and global hotkeys. A good example of PipeWire/PulseAudio graph manipulation. |
| [peripheral-battery-monitor](peripheral-battery-monitor/) | Compact always-on-top dashboard for Logitech, Keychron, Arctis, and AirPods battery monitoring. Demonstrates BLE scanning, upower/solaar integration, and KDE Wayland window rules. |
| [game-desktop-creator](game-desktop-creator/) | PyQt6 GUI for creating start menu launchers for Steam, Epic (via Heroic), and GOG games. Useful for Linux gaming setups. |
| [claude-code-global](claude-code-global/) | Global `CLAUDE.md` config implementing the Ralph Wiggum autonomous coding methodology—spec-driven, iterative development with quality gates and fresh context per iteration. |

## Projects

| Project | Description |
| :--- | :--- |
| [alacritty-maximizer](alacritty-maximizer/) | PyQt6 GUI to launch Alacritty windows fully maximized on specific monitors without titlebars. Manages KWin rules automatically. |
| [audio-source-switcher](audio-source-switcher/) | Feature-rich audio manager with priority auto-switching, mic association, Bluetooth device management, JamesDSP integration, and global hotkeys. |
| [claude-code-global](claude-code-global/) | Global `CLAUDE.md` config implementing the Ralph Wiggum autonomous coding methodology. |
| [claude-code-setup](claude-code-setup/) | Setup script for Claude Code CLI. Installs/updates Node.js and `@anthropic-ai/claude-code` globally. |
| [claude-usage-widget-windows](claude-usage-widget-windows/) | Windows system tray widget displaying Claude Code CLI usage metrics with floating progress bar, calibration, and configurable session windows. |
| [docker-setup](docker-setup/) | Sets up Docker for the current user. Installs Docker if missing, enables the service, and adds user to the `docker` group. |
| [fake-screensaver](fake-screensaver/) | PyQt-based fake screensaver that keeps the mouse cursor visible, plus a simple HTML blank page fallback. |
| [game-desktop-creator](game-desktop-creator/) | PyQt6 GUI for creating start menu launchers for Steam, Epic, and GOG games. Discovers games from Steam and Heroic Games Launcher. |
| [kvm-setup](kvm-setup/) | Setup scripts for KVM (QEMU/libvirt) on CachyOS. Configures libvirt group and permissions. |
| [misc](misc/) | General utilities for NTFS mount fixing and fstab generation during Windows-to-Linux migration. |
| [peripheral-battery-monitor](peripheral-battery-monitor/) | Compact always-on-top dashboard for Logitech, Keychron, Arctis, and AirPods battery monitoring. |
| [pinball-fx](pinball-fx/) | Window Fixer utility for Pinball FX. Forces the game onto selected monitors with persistent KWin rules. |
| [plasmashell-restart](plasmashell-restart/) | Restarts or refreshes the KDE Plasma 6 shell via systemd or D-Bus. |
| [qbittorrent-vpn-wrapper](qbittorrent-vpn-wrapper/) | Secure wrapper for qBittorrent with VPN binding, IP geolocation check, idle auto-shutdown, and status dashboard. |
| [set-rgb](set-rgb/) | Controls RGB lighting on hardware devices via OpenRGB, liquidctl, and ckb-next. |
| [the-great-cachyos-move](the-great-cachyos-move/) | Migration toolkit for moving CachyOS (Btrfs) installations between drives using `btrfs send/receive`. |
| [vpn-toggle](vpn-toggle/) | VPN manager with integrated monitoring, health checking, auto-reconnect, and persistent PyQt6 GUI for NetworkManager connections. |

## Usage

Refer to individual scripts for specific usage instructions. Most Python scripts use `argparse` and support `-h/--help`.
