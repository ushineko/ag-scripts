#!/bin/bash
set -e

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
DESKTOP_FILE="peripheral-battery-monitor.desktop"
AUTOSTART_DIR="$HOME/.config/autostart"
LOCAL_APPS_DIR="$HOME/.local/share/applications"

echo "Installing Peripheral Battery Monitor..."

# Ensure executable bit
chmod +x "$SCRIPT_DIR/peripheral-battery.py"

# Update desktop file with correct path if needed
sed -i "s|Exec=.*|Exec=/usr/bin/python3 $SCRIPT_DIR/peripheral-battery.py|" "$SCRIPT_DIR/$DESKTOP_FILE"

echo "Deploying desktop entry..."

# Ask user where to install
echo "Where would you like to install the desktop entry?"
echo "1) Autostart (starts on login)"
echo "2) Applications menu only"
echo "3) Both"
read -r -p "Select [1-3]: " choice

case $choice in
    1)
        mkdir -p "$AUTOSTART_DIR"
        cp "$SCRIPT_DIR/$DESKTOP_FILE" "$AUTOSTART_DIR/"
        echo "Installed to Autostart."
        ;;
    2)
        mkdir -p "$LOCAL_APPS_DIR"
        cp "$SCRIPT_DIR/$DESKTOP_FILE" "$LOCAL_APPS_DIR/"
        echo "Installed to Applications menu."
        ;;
    3)
        mkdir -p "$AUTOSTART_DIR"
        mkdir -p "$LOCAL_APPS_DIR"
        cp "$SCRIPT_DIR/$DESKTOP_FILE" "$AUTOSTART_DIR/"
        cp "$SCRIPT_DIR/$DESKTOP_FILE" "$LOCAL_APPS_DIR/"
        echo "Installed to Autostart and Applications menu."
        ;;
    *)
        echo "Invalid choice. Exiting."
        exit 1
        ;;
esac


# Install KWin rule if on KDE
if [ "$XDG_SESSION_DESKTOP" == "KDE" ] || [ "$DESKTOP_SESSION" == "plasma" ]; then
    echo "Detected KDE Plasma. Installing 'Always on Top' window rule..."
    python3 "$SCRIPT_DIR/install_kwin_rule.py" || echo "Warning: Failed to install KWin rule."
fi

echo "Installation complete!"
