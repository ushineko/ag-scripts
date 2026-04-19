#!/bin/bash

# Ensure we are in the script's directory
cd "$(dirname "$0")"

echo "Uninstalling Alacritty Maximizer..."

# 1. Remove KWin Rules
echo "Removing KWin Rules..."
python3 install_kwin_rules.py --uninstall

# 2. Remove KWin Script
SCRIPT_DEST="$HOME/.local/share/kwin/scripts/alacritty-maximizer"
if [ -d "$SCRIPT_DEST" ]; then
    rm -rf "$SCRIPT_DEST"
    echo "Removed KWin script at $SCRIPT_DEST"
else
    echo "KWin script directory not found."
fi

# Disable the script entry in kwinrc
if command -v kwriteconfig6 >/dev/null 2>&1; then
    kwriteconfig6 --file kwinrc --group Plugins --key alacrittyMaximizerEnabled false
elif command -v kwriteconfig5 >/dev/null 2>&1; then
    kwriteconfig5 --file kwinrc --group Plugins --key alacrittyMaximizerEnabled false
fi

if command -v qdbus6 >/dev/null 2>&1; then
    qdbus6 org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true
elif command -v qdbus >/dev/null 2>&1; then
    qdbus org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true
fi

# 3. Remove Desktop File
DESKTOP_FILE="$HOME/.local/share/applications/alacritty-maximizer.desktop"
if [ -f "$DESKTOP_FILE" ]; then
    rm "$DESKTOP_FILE"
    echo "Removed $DESKTOP_FILE"
else
    echo "Desktop file not found."
fi

# 4. Remove Autostart Entry
AUTOSTART_FILE="$HOME/.config/autostart/alacritty-maximizer.desktop"
if [ -f "$AUTOSTART_FILE" ]; then
    rm "$AUTOSTART_FILE"
    echo "Removed autostart entry $AUTOSTART_FILE"
else
    echo "Autostart entry not found."
fi

# 5. Remove config directory
CONFIG_DIR="$HOME/.config/alacritty-maximizer"
if [ -d "$CONFIG_DIR" ]; then
    rm -rf "$CONFIG_DIR"
    echo "Removed config directory $CONFIG_DIR"
else
    echo "Config directory not found."
fi

echo "Uninstallation complete."
