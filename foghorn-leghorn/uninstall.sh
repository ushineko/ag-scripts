#!/bin/bash
set -euo pipefail

APP_NAME="foghorn-leghorn"
INSTALL_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
CONFIG_DIR="$HOME/.config/foghorn-leghorn"

echo "Uninstalling Foghorn Leghorn..."

# Remove symlink
if [ -L "$INSTALL_DIR/$APP_NAME" ]; then
    rm "$INSTALL_DIR/$APP_NAME"
    echo "  Removed symlink: $INSTALL_DIR/$APP_NAME"
fi

# Remove desktop entry
if [ -f "$DESKTOP_DIR/$APP_NAME.desktop" ]; then
    rm "$DESKTOP_DIR/$APP_NAME.desktop"
    echo "  Removed desktop entry: $DESKTOP_DIR/$APP_NAME.desktop"
fi

# Update desktop database
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

# Optionally remove config
if [ -d "$CONFIG_DIR" ]; then
    read -rp "Remove configuration and saved timers at $CONFIG_DIR? (y/N): " response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        rm -rf "$CONFIG_DIR"
        echo "  Removed config: $CONFIG_DIR"
    else
        echo "  Config preserved at: $CONFIG_DIR"
    fi
fi

echo "Uninstallation complete."
