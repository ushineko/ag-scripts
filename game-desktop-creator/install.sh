#!/bin/bash
# Install Game Desktop Creator to the applications menu

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="game-desktop-creator"
DESKTOP_FILE="$APP_NAME.desktop"
INSTALL_DIR="$HOME/.local/share/applications"

echo "Installing Game Desktop Creator..."

# Create install directory if needed
mkdir -p "$INSTALL_DIR"

# Create desktop file with correct path
MAIN_SCRIPT="$SCRIPT_DIR/game_desktop_creator.py"
sed "s|EXEC_PATH|$MAIN_SCRIPT|g" "$SCRIPT_DIR/$DESKTOP_FILE" > "$INSTALL_DIR/$DESKTOP_FILE"

# Make executable
chmod +x "$INSTALL_DIR/$DESKTOP_FILE"
chmod +x "$MAIN_SCRIPT"

# Update desktop database
update-desktop-database "$INSTALL_DIR" 2>/dev/null || true

echo "Installation complete!"
echo "You can now find 'Game Desktop Creator' in your applications menu."
