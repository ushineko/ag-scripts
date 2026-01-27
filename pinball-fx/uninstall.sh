#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST_DESKTOP="$HOME/.local/share/applications/PinballFixer.desktop"
ICON_DEST="$HOME/.local/share/icons/hicolor/256x256/apps/pinball-fx.png"

echo "Removing Desktop file..."
rm -f "$DEST_DESKTOP"

echo "Removing Icon..."
rm -f "$ICON_DEST"

echo "Removing KWin Rules..."
"$SCRIPT_DIR/configure_kwin.py" --uninstall

echo "Updating caches..."
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null
if command -v kbuildsycoca6 &> /dev/null; then
    kbuildsycoca6 --noincremental
fi

echo "Uninstallation Complete."
