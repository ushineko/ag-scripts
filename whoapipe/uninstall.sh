#!/bin/bash

# Configuration
APP_NAME="whoapipe"
INSTALL_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$APP_NAME.desktop"
CONFIG_DIR="$HOME/.config/whoapipe"

echo "Uninstalling $APP_NAME..."

# 1. Remove desktop file
if [ -f "$INSTALL_DIR/$DESKTOP_FILE" ]; then
    rm "$INSTALL_DIR/$DESKTOP_FILE"
    echo "Removed $INSTALL_DIR/$DESKTOP_FILE"
else
    echo "Desktop file not found at $INSTALL_DIR/$DESKTOP_FILE"
fi

# 2. Update database
echo "Updating desktop database..."
update-desktop-database "$INSTALL_DIR"

# 3. Offer to remove config
if [ -d "$CONFIG_DIR" ]; then
    read -p "Remove config directory $CONFIG_DIR? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$CONFIG_DIR"
        echo "Removed $CONFIG_DIR"
    else
        echo "Config directory kept."
    fi
fi

echo "Uninstallation complete."
