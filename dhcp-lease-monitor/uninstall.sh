#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="dhcp-lease-monitor"
AUTOSTART_DIR="$HOME/.config/autostart"
LOCAL_APPS_DIR="$HOME/.local/share/applications"

echo "Uninstalling DHCP Lease Monitor..."

if [[ -f "$AUTOSTART_DIR/$APP_NAME.desktop" ]]; then
    rm "$AUTOSTART_DIR/$APP_NAME.desktop"
    echo "Removed: $AUTOSTART_DIR/$APP_NAME.desktop"
fi

if [[ -f "$LOCAL_APPS_DIR/$APP_NAME.desktop" ]]; then
    rm "$LOCAL_APPS_DIR/$APP_NAME.desktop"
    echo "Removed: $LOCAL_APPS_DIR/$APP_NAME.desktop"
fi

update-desktop-database "$LOCAL_APPS_DIR" >/dev/null 2>&1 || true

if [[ -f "$SCRIPT_DIR/install_kwin_rule.py" ]]; then
    python3 "$SCRIPT_DIR/install_kwin_rule.py" --uninstall || true
fi

if [[ -f "$HOME/.config/$APP_NAME.json" ]]; then
    rm "$HOME/.config/$APP_NAME.json"
    echo "Removed config: $HOME/.config/$APP_NAME.json"
fi

if [[ -d "$HOME/.local/state/$APP_NAME" ]]; then
    rm -rf "$HOME/.local/state/$APP_NAME"
    echo "Removed logs: $HOME/.local/state/$APP_NAME"
fi

echo "Uninstallation complete."
