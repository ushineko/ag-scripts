#!/bin/bash

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAUNCHER_SCRIPT="$SCRIPT_DIR/configure_kwin.py"
DESKTOP_FILE="$SCRIPT_DIR/PinballFixer.desktop"

DEST_DESKTOP="$HOME/.local/share/applications/PinballFixer.desktop"

# Ensure executable
chmod +x "$LAUNCHER_SCRIPT"

# Install Desktop File
echo "Installing Desktop file to $DEST_DESKTOP..."
cp "$SCRIPT_DIR/PinballFixer.desktop" "$DEST_DESKTOP"

# Install Icon (Optional, using system icon for now in desktop file, but keeping this if we want a custom one later)
# The desktop file uses 'dialog-ok-apply' for now, but we can reuse the pinball icon if we want.


# Setup KWin Rules
echo "Configuring KWin Rules..."
"$SCRIPT_DIR/configure_kwin.py"


# Update Icon Path in Desktop File if we find a better icon or if we need to copy it
# For now, we assume the desktop file points to the right place or we fix it here.
# (The desktop file assumes absolute path, which is fine)

# Notify
echo "Installation Complete!"
echo "You can launch 'Pinball FX' from your application menu."
