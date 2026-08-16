#!/bin/bash

# Configuration
APP_NAME="megabonker"
DESKTOP_FILE="$APP_NAME.desktop"
INSTALL_DIR="$HOME/.local/share/applications"
BIN_DIR="$HOME/.local/bin"
SCRIPT_PATH="$(cd "$(dirname "$0")" && pwd)/megabonker.py"

echo "Installing $APP_NAME..."

# 1. Check runtime dependencies before installing anything.
MISSING=""
for mod in PyQt6 cryptography numpy; do
    if ! /usr/bin/python3 -c "import $mod" 2>/dev/null; then
        MISSING="$MISSING $mod"
    fi
done
if [ -n "$MISSING" ]; then
    echo "Error: missing Python modules:$MISSING"
    echo "On Arch/CachyOS install them with:"
    echo "  sudo pacman -S python-pyqt6 python-cryptography python-numpy"
    exit 1
fi

# 2. Install desktop file
if [ -f "./$DESKTOP_FILE" ]; then
    echo "Installing desktop file to $INSTALL_DIR/$DESKTOP_FILE"
    mkdir -p "$INSTALL_DIR"
    cp "./$DESKTOP_FILE" "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/$DESKTOP_FILE"
else
    echo "Error: $DESKTOP_FILE not found in current directory!"
    exit 1
fi

# 3. Install CLI symlink in ~/.local/bin
mkdir -p "$BIN_DIR"
chmod +x "$SCRIPT_PATH"
ln -sfn "$SCRIPT_PATH" "$BIN_DIR/$APP_NAME"
echo "Installed CLI symlink: $BIN_DIR/$APP_NAME -> $SCRIPT_PATH"

# 4. Update database
if command -v update-desktop-database >/dev/null; then
    echo "Updating desktop database..."
    update-desktop-database "$INSTALL_DIR"
fi

echo "Done! Launch '$APP_NAME' from your application menu or the command line."
