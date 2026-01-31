# set-rgb

A simple script to unify RGB control across heterogenous usage of `OpenRGB`, `liquidctl`, and `ckb-next`.

## Prerequisites

You need to install the drivers for your specific hardware:

1.  **OpenRGB**: Controls Motherboard, GPU, generic RAM, etc.
    *   Arch: `sudo pacman -S openrgb`
    *   Debian/Ubuntu: `sudo apt install openrgb`
    *   Ensure you have the `openrgb-udev-rules` package or equivalent installed so you don't need `sudo`.

2.  **liquidctl**: Controls Corsair AIO Coolers, Commander Pro/Core.
    *   Pip: `pip install liquidctl`
    *   Arch: `sudo pacman -S liquidctl`

3.  **ckb-next**: Controls Corsair Peripherals (Mouse, Keyboard, Mousepad).
    *   Arch: `yay -S ckb-next` (AUR) or build from source.
    *   **Important**: The `ckb-next-daemon` service must be running.

## Usage

```bash
python3 change_color.py <color>
```

Supported colors: `red`, `green`, `blue`, `white`, `off`.

## Troubleshooting

-   **I2C / SMBus Errors (OpenRGB)**: If you see errors about I2C or devices not detected, your user likely needs to be in the `i2c` group.
    1.  Run `sudo usermod -aG i2c $USER`
    2.  Log out and back in.
    3.  Ensure `i2c-dev` module is loaded: `sudo modprobe i2c-dev`

-   **Permission Denied**: If the script fails to set colors, try running with `sudo` or ensure your user has access to the USB devices (setup udev rules).
-   **Devices not found (OpenRGB)**: Run `openrgb --server` once to initialize or run the GUI to scan for devices.
-   **Mousepad not changing**: Ensure `ckb-next-daemon` is active. Check `/run/ckb-next-cmd` exists.

## Changelog

### v1.0.0
- Initial release
- Unified control for OpenRGB, liquidctl, and ckb-next
- Support for basic colors (red, green, blue, white, off)
