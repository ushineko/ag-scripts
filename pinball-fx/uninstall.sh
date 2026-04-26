#!/bin/bash
# Uninstall the Pinball FX gamescope wrapper (v3.0.0).
#
# Removes:
# - v1.x PinballFixer.desktop and v2.x PinballFX.desktop entries (if present).
# - The hicolor icon (if present from older installs).
# - Current and legacy KWin rules ('Pinball FX Gamescope Placement' and
#   'Pinball FX Portrait Mode').
#
# Does NOT touch Heroic's per-game config — if you set a Wrapper Command or
# changed the Wine version in Heroic for Pinball FX, undo those manually in
# Heroic's GUI.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPS_DIR="$HOME/.local/share/applications"

echo "Removing legacy desktop entries..."
rm -f "$APPS_DIR/PinballFX.desktop" "$APPS_DIR/PinballFixer.desktop"

echo "Removing hicolor icon (if any)..."
rm -f "$HOME/.local/share/icons/hicolor/256x256/apps/pinball-fx.png"

echo "Removing KWin rules..."
if [ -x "$SCRIPT_DIR/install_kwin_rule.py" ]; then
    "$SCRIPT_DIR/install_kwin_rule.py" --uninstall
else
    echo "install_kwin_rule.py not found or not executable; skipping rule removal."
fi

echo "Updating caches..."
update-desktop-database "$APPS_DIR" 2>/dev/null || true
if command -v kbuildsycoca6 &> /dev/null; then
    kbuildsycoca6 --noincremental 2>/dev/null || true
fi

cat <<EOF

Uninstallation complete.

Reminder: if you set Heroic's per-game "Wrapper Command" or changed the Wine
version for Pinball FX, undo those manually in the Heroic GUI:
  Pinball FX → Settings → Wine version → reset
  Pinball FX → Settings → Wrapper Command → clear
EOF
