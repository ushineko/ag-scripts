#!/bin/bash

# Configuration
APP_NAME="audio-source-switcher"
INSTALL_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$APP_NAME.desktop"

echo "Uninstalling $APP_NAME..."

if [ -f "$INSTALL_DIR/$DESKTOP_FILE" ]; then
    rm "$INSTALL_DIR/$DESKTOP_FILE"
    echo "Removed $INSTALL_DIR/$DESKTOP_FILE"
else
    echo "Desktop file not found at $INSTALL_DIR/$DESKTOP_FILE"
fi

echo "Updating desktop database..."
update-desktop-database "$INSTALL_DIR"

echo "Uninstallation complete."
