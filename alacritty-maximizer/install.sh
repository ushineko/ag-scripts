#!/bin/bash

# Ensure we are in the script's directory
cd "$(dirname "$0")"

echo "Installing Alacritty Maximizer..."

# 1. Install KWin Rules
echo "Installing KWin Rules..."
python3 install_kwin_rules.py

# 2. Install Desktop File
APP_DIR="$HOME/.local/share/applications"
mkdir -p "$APP_DIR"

DESKTOP_FILE="alacritty-maximizer.desktop"
TARGET_PATH="$APP_DIR/$DESKTOP_FILE"

# We need to make sure the Exec path in the desktop file is absolute
# Get current absolute path
CURRENT_DIR=$(pwd)
MAIN_SCRIPT="$CURRENT_DIR/main.py"

# Create a temporary desktop file with the correct Exec path
cp "$DESKTOP_FILE" "$DESKTOP_FILE.tmp"
sed -i "s|EXEC_PATH|$MAIN_SCRIPT|g" "$DESKTOP_FILE.tmp"
sed -i "s|ICON_PATH|utilities-terminal|g" "$DESKTOP_FILE.tmp"

mv "$DESKTOP_FILE.tmp" "$TARGET_PATH"

echo "Installed desktop file to $TARGET_PATH"

# 3. Install Autostart Entry
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"

AUTOSTART_TARGET="$AUTOSTART_DIR/alacritty-maximizer.desktop"
cat > "$AUTOSTART_TARGET" <<DESKTOP
[Desktop Entry]
Name=Alacritty Maximizer (Autostart)
Comment=Auto-launch Alacritty on saved default monitor
Exec=python3 $MAIN_SCRIPT --autostart
Icon=utilities-terminal
Type=Application
Categories=Utility;Terminal;
Terminal=false
X-KDE-autostart-phase=2
DESKTOP

echo "Installed autostart entry to $AUTOSTART_TARGET"

echo ""
echo "Done! You can now launch 'Alacritty Maximizer' from your application menu."
echo ""
echo "To enable auto-launch on login:"
echo "  1. Launch Alacritty Maximizer from the app menu"
echo "  2. Select a monitor and check 'Save as default'"
echo "  3. Check 'Launch on login (KDE autostart)'"
echo "  4. Click Launch"
echo ""
echo "The autostart entry is installed but inactive until you enable it in the GUI."
