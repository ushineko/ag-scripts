#!/bin/bash

# Configuration
APP_NAME="peripheral-battery-monitor"
DESKTOP_FILE="$APP_NAME.desktop"
AUTOSTART_DIR="$HOME/.config/autostart"
LOCAL_APPS_DIR="$HOME/.local/share/applications"

echo "Uninstalling $APP_NAME..."

# 1. Remove Desktop Files
if [ -f "$AUTOSTART_DIR/$DESKTOP_FILE" ]; then
    rm "$AUTOSTART_DIR/$DESKTOP_FILE"
    echo "Removed from Autostart."
fi

if [ -f "$LOCAL_APPS_DIR/$DESKTOP_FILE" ]; then
    rm "$LOCAL_APPS_DIR/$DESKTOP_FILE"
    echo "Removed from Applications menu."
fi

# 2. Remove KWin Rules
echo "Removing KWin Rules..."
python3 install_kwin_rule.py --uninstall

echo "Uninstallation complete."
