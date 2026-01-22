#!/usr/bin/env python3
import subprocess
import argparse
import sys
import os

# Defined colors
COLORS = {
    "red": {"hex": "#FF0000", "rgb": (255, 0, 0)},
    "green": {"hex": "#00FF00", "rgb": (0, 255, 0)},
    "blue": {"hex": "#0000FF", "rgb": (0, 0, 255)},
    "white": {"hex": "#FFFFFF", "rgb": (255, 255, 255)},
    "off": {"hex": "#000000", "rgb": (0, 0, 0)},
}

def check_tool(tool_name):
    """Check if a tool is available in the path."""
    return subprocess.call(
        ["which", tool_name], 
        stdout=subprocess.DEVNULL, 
        stderr=subprocess.DEVNULL
    ) == 0

def set_openrgb(color_hex):
    """Set color using OpenRGB."""
    if not check_tool("openrgb"):
        print("[!] openrgb not found. Skipping OpenRGB devices.")
        return

    print(f"[*] Setting OpenRGB devices to {color_hex}...")
    try:
        # Using a timeout to prevent hanging if I2C freezes
        # -c sets all devices
        # We explicitly set mode to 'Direct' as it is the common supported mode for GPU, Mobo, etc.
        # 'Static' is not supported by the MSI GPU.
        subprocess.run(
            ["openrgb", "--mode", "Direct", "--color", color_hex], 
            check=False, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL,
            timeout=5
        )
    except subprocess.TimeoutExpired:
        print("[!] OpenRGB timed out.")
    except Exception as e:
        print(f"[!] Failed to run openrgb: {e}")

def set_liquidctl(color_rgb):
    """Set color using liquidctl."""
    if not check_tool("liquidctl"):
        print("[!] liquidctl not found. Skipping Corsair AIO/Commander.")
        return

    r, g, b = color_rgb
    print(f"[*] Setting liquidctl devices to {r},{g},{b}...")
    
    try:
        # List devices first
        result = subprocess.check_output(["liquidctl", "list"], text=True)
        devices = []
        for line in result.splitlines():
            # Example: Device #0: Corsair Commander ST (broken)
            if "Device #" in line:
                # We attempt even if broken, as sometimes lighting control still works
                # Format: Device #ID: Description
                parts = line.split(":", 1)
                if len(parts) == 2:
                    dev_desc = parts[1].strip()
                    # Remove '(broken)' text for cleaner logging if preferred, 
                    # but for matching we might need the exact string or just the name. 
                    # liquidctl match uses substring.
                    devices.append(dev_desc)

        if not devices:
            print("[!] No valid liquidctl devices found.")
            return

        for dev in devices:
            print(f"    - Setting {dev}...")
            # We used 'fixed' mode before. Some devices want 'sync' or just different modes.
            # 'fixed' is standard for AIOs/Commanders.
            # Try/Except for each device
            try:
                subprocess.run(  
                    ["liquidctl", "--match", dev, "set", "led", "color", "fixed", str(r), str(g), str(b)],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE
                )
            except Exception as e:
                print(f"      [!] Error setting {dev}: {e}")
                
    except Exception as e:
        print(f"[!] Failed to run liquidctl list: {e}")

def set_ckb_next(color_hex):
    """Set color using ckb-next pipe."""
    # ckb-next daemon typically listens on a pipe /run/ckb-next-cmd or /tmp/ckb-next-cmd
    pipes = ["/run/ckb-next-cmd", "/tmp/ckb-next-cmd"]
    active_pipe = None
    
    for p in pipes:
        if os.path.exists(p):
            active_pipe = p
            break
            
    if not active_pipe:
        print("[!] ckb-next command pipe not found. Attempting to start ckb-next-daemon...")
        try:
            # Try to start the service using systemctl
            subprocess.run(["sudo", "systemctl", "start", "ckb-next-daemon"], check=False)
            # Wait a moment for the pipe to appear
            import time
            time.sleep(2)
            
            # Check pipes again
            for p in pipes:
                if os.path.exists(p):
                    active_pipe = p
                    break
        except Exception as e:
            print(f"[!] Failed to start ckb-next-daemon: {e}")

    if not active_pipe:
        print("[!] ckb-next-daemon still not running. Skipping Mousepad.")
        return

    print(f"[*] Setting ckb-next devices (Mousepad) to {color_hex}...")
    try:
        # Command format: "rgb <color>" or specific to device.
        # Sending "rgb <hex>" usually sets global color.
        with open(active_pipe, "w") as f:
            f.write(f"rgb {color_hex}\n")
    except Exception as e:
        print(f"[!] Failed to write to ckb-next pipe: {e}")

def main():
    parser = argparse.ArgumentParser(description="Set RGB colors for all devices.")
    parser.add_argument("color", choices=COLORS.keys(), help="Color to set devices to.")
    args = parser.parse_args()

    color_info = COLORS[args.color]
    color_hex = color_info["hex"]
    color_rgb = color_info["rgb"]

    print(f"Applying color: {args.color.upper()} ({color_hex})")
    
    set_openrgb(color_hex.replace("#", "")) # OpenRGB often prefers Hex without # or separated. Let's try standard.
    # Actually OpenRGB arg parsing is annoying. hex without # is safest often.
    
    set_liquidctl(color_rgb)
    set_ckb_next(color_hex)
    
    print("\n[=] Done. Note: Some tools might need sudo if udev rules are not set.")

if __name__ == "__main__":
    main()
