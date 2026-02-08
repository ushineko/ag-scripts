#!/bin/bash

# Ensure we are in the script's directory
cd "$(dirname "$0")"

echo "Uninstalling Alacritty Maximizer..."

# 1. Remove KWin Rules
echo "Removing KWin Rules..."
python3 install_kwin_rules.py --uninstall

# 2. Remove Desktop File
DESKTOP_FILE="$HOME/.local/share/applications/alacritty-maximizer.desktop"
if [ -f "$DESKTOP_FILE" ]; then
    rm "$DESKTOP_FILE"
    echo "Removed $DESKTOP_FILE"
else
    echo "Desktop file not found."
fi

# 3. Remove Autostart Entry
AUTOSTART_FILE="$HOME/.config/autostart/alacritty-maximizer.desktop"
if [ -f "$AUTOSTART_FILE" ]; then
    rm "$AUTOSTART_FILE"
    echo "Removed autostart entry $AUTOSTART_FILE"
else
    echo "Autostart entry not found."
fi

# 4. Remove config directory
CONFIG_DIR="$HOME/.config/alacritty-maximizer"
if [ -d "$CONFIG_DIR" ]; then
    rm -rf "$CONFIG_DIR"
    echo "Removed config directory $CONFIG_DIR"
else
    echo "Config directory not found."
fi

echo "Uninstallation complete."
