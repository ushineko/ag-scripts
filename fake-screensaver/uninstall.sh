#!/bin/bash

APP_NAME="fake-screensaver"
DESKTOP_FILE="$HOME/.local/share/applications/fake-screensaver.desktop"

echo "Uninstalling $APP_NAME..."

if [ -f "$DESKTOP_FILE" ]; then
    rm "$DESKTOP_FILE"
    echo "Removed $DESKTOP_FILE"
else
    echo "Desktop file not found at $DESKTOP_FILE"
fi

echo "Uninstallation complete."
