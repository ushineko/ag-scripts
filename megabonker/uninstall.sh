#!/bin/bash

# Configuration
APP_NAME="megabonker"
DESKTOP_FILE="$APP_NAME.desktop"
INSTALL_DIR="$HOME/.local/share/applications"
BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/$APP_NAME"

PURGE=0
for arg in "$@"; do
    case "$arg" in
        --purge) PURGE=1 ;;
        -h|--help)
            cat <<USAGE
Usage: $0 [--purge]

  --purge   Also remove $CONFIG_DIR, which holds preferences and the
            keyring of re-derived save keys. Save file backups written
            next to your saves are never touched.
USAGE
            exit 0
            ;;
    esac
done

echo "Uninstalling $APP_NAME..."

if [ -f "$INSTALL_DIR/$DESKTOP_FILE" ]; then
    rm "$INSTALL_DIR/$DESKTOP_FILE"
    echo "Removed $INSTALL_DIR/$DESKTOP_FILE"
fi

if [ -L "$BIN_DIR/$APP_NAME" ]; then
    rm "$BIN_DIR/$APP_NAME"
    echo "Removed $BIN_DIR/$APP_NAME"
fi

if [ "$PURGE" = "1" ] && [ -d "$CONFIG_DIR" ]; then
    rm -rf "$CONFIG_DIR"
    echo "Removed $CONFIG_DIR"
elif [ -d "$CONFIG_DIR" ]; then
    echo "Kept $CONFIG_DIR (use --purge to remove preferences and saved keys)"
fi

if command -v update-desktop-database >/dev/null; then
    update-desktop-database "$INSTALL_DIR"
fi

echo "Done."
