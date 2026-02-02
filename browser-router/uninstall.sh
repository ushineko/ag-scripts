#!/bin/bash
# uninstall.sh - Remove browser-router and restore Vivaldi as default browser

set -euo pipefail

echo "Uninstalling Browser Router..."

# 1. Remove script from ~/.local/bin
BIN_FILE="$HOME/.local/bin/browser-router"
if [[ -f "$BIN_FILE" ]]; then
    rm -f "$BIN_FILE"
    echo "Removed $BIN_FILE"
else
    echo "Script not found at $BIN_FILE (already removed?)"
fi

# 2. Remove desktop file
DESKTOP_FILE="$HOME/.local/share/applications/browser-router.desktop"
if [[ -f "$DESKTOP_FILE" ]]; then
    rm -f "$DESKTOP_FILE"
    echo "Removed $DESKTOP_FILE"
else
    echo "Desktop file not found at $DESKTOP_FILE (already removed?)"
fi

# 3. Update desktop database
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

# 4. Restore Vivaldi as default browser
MIMEAPPS="$HOME/.config/mimeapps.list"
if [[ -f "$MIMEAPPS" ]]; then
    sed -i 's|^x-scheme-handler/http=browser-router.desktop|x-scheme-handler/http=vivaldi-stable.desktop|' "$MIMEAPPS"
    sed -i 's|^x-scheme-handler/https=browser-router.desktop|x-scheme-handler/https=vivaldi-stable.desktop|' "$MIMEAPPS"
    echo "Restored Vivaldi as default browser for http/https"
else
    echo "No mimeapps.list found - browser defaults unchanged"
fi

echo ""
echo "Done! Browser Router has been uninstalled."
echo "Vivaldi is now your default browser for all URLs."
