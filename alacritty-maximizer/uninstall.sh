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

echo "Uninstallation complete."
