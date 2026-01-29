#!/bin/bash
# Uninstall Steam Desktop File Creator

set -e

APP_NAME="steam-desktop-creator"
DESKTOP_FILE="$APP_NAME.desktop"
INSTALL_DIR="$HOME/.local/share/applications"
ICONS_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"

echo "Uninstalling Steam Desktop File Creator..."

# Remove application desktop file
if [ -f "$INSTALL_DIR/$DESKTOP_FILE" ]; then
    rm "$INSTALL_DIR/$DESKTOP_FILE"
    echo "Removed application launcher"
fi

# Ask about removing game desktop files
GAME_FILES=$(find "$INSTALL_DIR" -name "steam-game-*.desktop" 2>/dev/null | wc -l)
if [ "$GAME_FILES" -gt 0 ]; then
    echo ""
    echo "Found $GAME_FILES Steam game desktop file(s)."
    read -r -p "Remove all game launchers? [y/N] " response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        rm -f "$INSTALL_DIR"/steam-game-*.desktop
        echo "Removed game desktop files"

        # Also remove game icons
        if [ -d "$ICONS_DIR" ]; then
            rm -f "$ICONS_DIR"/steam-game-*.png
            echo "Removed game icons"
        fi
    fi
fi

# Update desktop database
update-desktop-database "$INSTALL_DIR" 2>/dev/null || true

echo "Uninstallation complete!"
