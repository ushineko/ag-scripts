#!/bin/bash
# install.sh - Install browser-router as the default browser handler

set -euo pipefail

cd "$(dirname "$0")"

echo "Installing Browser Router..."

# 1. Install script to ~/.local/bin
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"

SCRIPT_PATH="$(pwd)/browser-router.sh"
TARGET_BIN="$BIN_DIR/browser-router"

cp "$SCRIPT_PATH" "$TARGET_BIN"
chmod +x "$TARGET_BIN"
echo "Installed script to $TARGET_BIN"

# 2. Install desktop file
APP_DIR="$HOME/.local/share/applications"
mkdir -p "$APP_DIR"

DESKTOP_FILE="browser-router.desktop"
TARGET_DESKTOP="$APP_DIR/$DESKTOP_FILE"

cp "$DESKTOP_FILE" "$TARGET_DESKTOP"
sed -i "s|EXEC_PATH|$TARGET_BIN|g" "$TARGET_DESKTOP"
echo "Installed desktop file to $TARGET_DESKTOP"

# 3. Update desktop database
update-desktop-database "$APP_DIR" 2>/dev/null || true

# 4. Set as default for http/https
MIMEAPPS="$HOME/.config/mimeapps.list"

# Backup existing mimeapps.list
if [[ -f "$MIMEAPPS" ]]; then
    cp "$MIMEAPPS" "$MIMEAPPS.backup.$(date +%Y%m%d%H%M%S)"
fi

# Update or add http/https handlers
if grep -q "^\[Default Applications\]" "$MIMEAPPS" 2>/dev/null; then
    # Update existing entries
    sed -i 's|^x-scheme-handler/http=.*|x-scheme-handler/http=browser-router.desktop|' "$MIMEAPPS"
    sed -i 's|^x-scheme-handler/https=.*|x-scheme-handler/https=browser-router.desktop|' "$MIMEAPPS"

    # Add if not present
    if ! grep -q "^x-scheme-handler/http=" "$MIMEAPPS"; then
        sed -i '/^\[Default Applications\]/a x-scheme-handler/http=browser-router.desktop' "$MIMEAPPS"
    fi
    if ! grep -q "^x-scheme-handler/https=" "$MIMEAPPS"; then
        sed -i '/^\[Default Applications\]/a x-scheme-handler/https=browser-router.desktop' "$MIMEAPPS"
    fi
else
    # Create new file with defaults
    cat >> "$MIMEAPPS" << EOF
[Default Applications]
x-scheme-handler/http=browser-router.desktop
x-scheme-handler/https=browser-router.desktop
EOF
fi

echo "Set browser-router as default for http/https"
echo ""
echo "Done! Browser Router is now your default browser handler."
echo "  - Teams URLs -> Firefox"
echo "  - All other URLs -> Vivaldi"
echo ""
echo "Edit $TARGET_BIN to customize URL routing patterns."
