#!/bin/bash

# Configuration
APP_NAME="qbittorrent-vpn-wrapper"
INSTALL_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="qbittorrent-secure.desktop"

echo "--- Uninstalling qBittorrent VPN Wrapper ---"

if [ -f "$INSTALL_DIR/$DESKTOP_FILE" ]; then
    rm "$INSTALL_DIR/$DESKTOP_FILE"
    echo "✓ Removed $INSTALL_DIR/$DESKTOP_FILE"
else
    echo "ℹ Desktop file not found at $INSTALL_DIR/$DESKTOP_FILE"
fi

if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$INSTALL_DIR"
    echo "✓ Desktop database updated."
fi

echo "--- Uninstallation Complete ---"
