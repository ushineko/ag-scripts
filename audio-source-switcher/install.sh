#!/bin/bash

# Configuration
APP_NAME="audio-source-switcher"
OLD_NAME="select-audio-source"
DESKTOP_FILE="$APP_NAME.desktop"
INSTALL_DIR="$HOME/.local/share/applications"

echo "Installing $APP_NAME..."

# 1. Remove old desktop file
if [ -f "$INSTALL_DIR/$OLD_NAME.desktop" ]; then
    echo "removing old desktop file: $INSTALL_DIR/$OLD_NAME.desktop"
    rm "$INSTALL_DIR/$OLD_NAME.desktop"
fi

# 2. Install new desktop file
if [ -f "./$DESKTOP_FILE" ]; then
    echo "Installing new desktop file to $INSTALL_DIR/$DESKTOP_FILE"
    cp "./$DESKTOP_FILE" "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/$DESKTOP_FILE"
else
    echo "Error: $DESKTOP_FILE not found in current directory!"
    exit 1
fi

# 3. Update database
echo "Updating desktop database..."
update-desktop-database "$INSTALL_DIR"

echo "Done! You can now launch '$APP_NAME' from your application menu."
