#!/usr/bin/env bash
# Remove herdr-switcher: stop the daemon, remove symlinks, desktop/autostart
# entries, and icon. Leaves ~/.config/herdr-switcher (config + MRU state) in
# place unless --purge is given.
set -euo pipefail

APP="herdr-switcher"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
AUTOSTART_DIR="$HOME/.config/autostart"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

# stop running daemon (it unregisters its global shortcut on quit)
pkill -f "herdr_switcher.py --tray" 2>/dev/null || true
pkill -f "$BIN_DIR/$APP --tray" 2>/dev/null || true

rm -f "$BIN_DIR/$APP" "$BIN_DIR/$APP-cli"
rm -f "$APP_DIR/$APP.desktop" "$AUTOSTART_DIR/$APP.desktop"
rm -f "$ICON_DIR/$APP.svg"

command -v kbuildsycoca6 >/dev/null 2>&1 && kbuildsycoca6 >/dev/null 2>&1 || true

if [[ "${1:-}" == "--purge" ]]; then
    rm -rf "$HOME/.config/herdr-switcher"
    echo "removed config + state (~/.config/herdr-switcher)"
fi

echo "herdr-switcher uninstalled."
echo "Note: if Ctrl+Meta+Tab stays captured, log out/in to clear the stale KGlobalAccel binding."
