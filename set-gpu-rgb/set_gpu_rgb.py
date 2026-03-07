#!/usr/bin/env python3
"""Set RGB color on the MSI GeForce RTX 4090 Suprim Liquid X via OpenRGB."""

import argparse
import socket
import subprocess
import sys
import time

__version__ = "1.0"

COLORS = {
    "red": "FF0000",
    "green": "00FF00",
    "blue": "0000FF",
    "white": "FFFFFF",
    "off": "000000",
}

GPU_DEVICE = 0
OPENRGB_PORT = 6742
SERVER_STARTUP_TIMEOUT = 20


def server_is_running():
    """Check if the OpenRGB SDK server is accepting connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        try:
            s.connect(("localhost", OPENRGB_PORT))
            return True
        except (ConnectionRefusedError, OSError):
            return False


def ensure_server():
    """Start the OpenRGB server if it isn't already running."""
    if server_is_running():
        return

    print("Starting OpenRGB server (this takes a few seconds)...")
    subprocess.Popen(
        ["openrgb", "--server", "--server-port", str(OPENRGB_PORT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.monotonic() + SERVER_STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        if server_is_running():
            # Give the server a moment to finish device enumeration
            time.sleep(2)
            return
        time.sleep(1)

    print("Error: OpenRGB server did not start in time.", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Set RGB color on the GPU (MSI RTX 4090 Suprim Liquid X)."
    )
    parser.add_argument(
        "color",
        nargs="?",
        choices=COLORS.keys(),
        help="Color to set. Omit to turn off.",
    )
    parser.add_argument(
        "--hex",
        metavar="RRGGBB",
        help="Arbitrary hex color (e.g. FF8800). Overrides positional color.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    args = parser.parse_args()

    if args.hex:
        hex_color = args.hex.lstrip("#").upper()
        if len(hex_color) != 6 or not all(c in "0123456789ABCDEF" for c in hex_color):
            print(f"Error: invalid hex color '{args.hex}'", file=sys.stderr)
            sys.exit(1)
    elif args.color:
        hex_color = COLORS[args.color]
    else:
        hex_color = COLORS["off"]

    ensure_server()

    print(f"Setting GPU RGB to #{hex_color}...")
    try:
        result = subprocess.run(
            [
                "openrgb",
                "--client", f"localhost:{OPENRGB_PORT}",
                "--device", str(GPU_DEVICE),
                "--mode", "Direct",
                "--color", hex_color,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            print(f"openrgb failed (exit {result.returncode}): {stderr}", file=sys.stderr)
            sys.exit(1)
    except FileNotFoundError:
        print("Error: openrgb not found. Install it first.", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("Error: openrgb timed out.", file=sys.stderr)
        sys.exit(1)

    print("Done.")


if __name__ == "__main__":
    main()
