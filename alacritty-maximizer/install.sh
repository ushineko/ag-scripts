#!/bin/bash

# Ensure we are in the script's directory
cd "$(dirname "$0")"

echo "Installing Alacritty Maximizer..."

# 1. Install KWin Rules
echo "Installing KWin Rules..."
python3 install_kwin_rules.py

# 2. Install Desktop File
APP_DIR="$HOME/.local/share/applications"
mkdir -p "$APP_DIR"

DESKTOP_FILE="alacritty-maximizer.desktop"
TARGET_PATH="$APP_DIR/$DESKTOP_FILE"

# We need to make sure the Exec path in the desktop file is absolute
# Get current absolute path
CURRENT_DIR=$(pwd)
MAIN_SCRIPT="$CURRENT_DIR/main.py"

# Create a temporary desktop file with the correct Exec path
cp "$DESKTOP_FILE" "$DESKTOP_FILE.tmp"
sed -i "s|EXEC_PATH|$MAIN_SCRIPT|g" "$DESKTOP_FILE.tmp"
sed -i "s|ICON_PATH|utilities-terminal|g" "$DESKTOP_FILE.tmp"

mv "$DESKTOP_FILE.tmp" "$TARGET_PATH"

echo "Installed desktop file to $TARGET_PATH"
echo "Done! You can now launch 'Alacritty Maximizer' from your application menu."
