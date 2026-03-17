#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

chmod +x "$SCRIPT_DIR/aiqlabs-vpn-toggle.sh"

cp "$SCRIPT_DIR/aiqlabs-vpn-toggle.desktop" ~/.local/share/applications/
update-desktop-database ~/.local/share/applications/ 2>/dev/null || true

echo "Installed aiqlabs-vpn-toggle.desktop to ~/.local/share/applications/"
echo ""
echo "Prerequisites:"
echo "  - openvpn3 installed (paru -S openvpn3)"
echo "  - Config imported: openvpn3 config-import --config <profile>.ovpn --name aiqlabs --persistent"
echo ""
echo "To add to taskbar:"
echo "  1. Search 'AIQLabs VPN' in application launcher"
echo "  2. Or: add a global shortcut in System Settings → Shortcuts → Custom Shortcuts"
echo "     Command: $SCRIPT_DIR/aiqlabs-vpn-toggle.sh toggle"
