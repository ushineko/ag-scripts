#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

chmod +x "$SCRIPT_DIR/facecam-toggle.sh"

cp "$SCRIPT_DIR/facecam-toggle.desktop" ~/.local/share/applications/
update-desktop-database ~/.local/share/applications/ 2>/dev/null || true

echo "Installed facecam-toggle.desktop to ~/.local/share/applications/"
echo ""
echo "To add to taskbar:"
echo "  1. Right-click Plasma panel → Add Widgets → search 'Application Launcher' or use existing"
echo "  2. Or: add a global shortcut in System Settings → Shortcuts → Custom Shortcuts"
echo "     Command: $SCRIPT_DIR/facecam-toggle.sh toggle"
