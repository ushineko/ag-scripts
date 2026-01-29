#!/bin/bash
# Uninstall Game Desktop Creator

set -e

APP_NAME="game-desktop-creator"
DESKTOP_FILE="$APP_NAME.desktop"
INSTALL_DIR="$HOME/.local/share/applications"
ICONS_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"

echo "Uninstalling Game Desktop Creator..."

# Remove application desktop file
if [ -f "$INSTALL_DIR/$DESKTOP_FILE" ]; then
    rm "$INSTALL_DIR/$DESKTOP_FILE"
    echo "Removed application launcher"
fi

# Count game desktop files
STEAM_FILES=$(find "$INSTALL_DIR" -name "steam-game-*.desktop" 2>/dev/null | wc -l)
HEROIC_FILES=$(find "$INSTALL_DIR" -name "heroic-*.desktop" 2>/dev/null | wc -l)
TOTAL_FILES=$((STEAM_FILES + HEROIC_FILES))

if [ "$TOTAL_FILES" -gt 0 ]; then
    echo ""
    echo "Found $TOTAL_FILES game desktop file(s) ($STEAM_FILES Steam, $HEROIC_FILES Heroic)."
    read -r -p "Remove all game launchers? [y/N] " response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        rm -f "$INSTALL_DIR"/steam-game-*.desktop
        rm -f "$INSTALL_DIR"/heroic-*.desktop
        echo "Removed game desktop files"

        # Also remove game icons
        if [ -d "$ICONS_DIR" ]; then
            rm -f "$ICONS_DIR"/steam-game-*.png
            rm -f "$ICONS_DIR"/heroic-game-*.png
            echo "Removed game icons"
        fi
    fi
fi

# Update desktop database
update-desktop-database "$INSTALL_DIR" 2>/dev/null || true

echo "Uninstallation complete!"
