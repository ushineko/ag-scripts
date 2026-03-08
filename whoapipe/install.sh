#!/bin/bash

# Configuration
APP_NAME="whoapipe"
DESKTOP_FILE="$APP_NAME.desktop"
INSTALL_DIR="$HOME/.local/share/applications"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing $APP_NAME..."

# 1. Install desktop file
mkdir -p "$INSTALL_DIR"
if [ -f "$SCRIPT_DIR/$DESKTOP_FILE" ]; then
    echo "Installing desktop file to $INSTALL_DIR/$DESKTOP_FILE"
    cp "$SCRIPT_DIR/$DESKTOP_FILE" "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/$DESKTOP_FILE"
else
    echo "Error: $DESKTOP_FILE not found in $SCRIPT_DIR!"
    exit 1
fi

# 2. Update database
echo "Updating desktop database..."
update-desktop-database "$INSTALL_DIR"

echo "Done! You can now launch '$APP_NAME' from your application menu."
