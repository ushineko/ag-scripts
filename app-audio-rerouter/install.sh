#!/bin/bash

APP_NAME="app-audio-rerouter"
DESKTOP_FILE="$APP_NAME.desktop"
INSTALL_DIR="$HOME/.local/share/applications"

echo "Installing $APP_NAME..."

if [ -f "./$DESKTOP_FILE" ]; then
    echo "Installing desktop file to $INSTALL_DIR/$DESKTOP_FILE"
    cp "./$DESKTOP_FILE" "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/$DESKTOP_FILE"
else
    echo "Error: $DESKTOP_FILE not found in current directory!"
    exit 1
fi

echo "Updating desktop database..."
update-desktop-database "$INSTALL_DIR"

echo "Done! You can now launch '$APP_NAME' from your application menu."
