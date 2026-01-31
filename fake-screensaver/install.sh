#!/bin/bash
set -e

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
DESKTOP_FILE="fake-screensaver.desktop"
LOCAL_APPS_DIR="$HOME/.local/share/applications"

echo "Installing Fake Screensaver..."

# Ensure executable bit
chmod +x "$SCRIPT_DIR/fake_screensaver.py"

# Update desktop file with correct path
sed -i "s|Exec=.*|Exec=$SCRIPT_DIR/fake_screensaver.py|" "$SCRIPT_DIR/$DESKTOP_FILE"

# Create applications directory if needed
mkdir -p "$LOCAL_APPS_DIR"

# Copy desktop file
cp "$SCRIPT_DIR/$DESKTOP_FILE" "$LOCAL_APPS_DIR/"

echo "Installation complete!"
echo "Fake Screensaver is now available in your applications menu."
echo ""
echo "Tip: Bind to a global hotkey (e.g., Meta+L) via System Settings -> Shortcuts"
