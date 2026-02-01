#!/usr/bin/env bash
#
# Uninstallation script for VPN Toggle v2.0
#

INSTALL_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
CONFIG_DIR="$HOME/.config/vpn-toggle"

echo "Uninstalling VPN Toggle v2.0..."

# Remove symlink
if [ -L "$INSTALL_DIR/vpn-toggle-v2" ]; then
    echo "Removing vpn-toggle-v2..."
    rm "$INSTALL_DIR/vpn-toggle-v2"
fi

# Remove desktop file
if [ -f "$DESKTOP_DIR/vpn-toggle-v2.desktop" ]; then
    echo "Removing desktop launcher..."
    rm "$DESKTOP_DIR/vpn-toggle-v2.desktop"

    # Update desktop database if available
    if command -v update-desktop-database &> /dev/null; then
        update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
    fi
fi

# Ask about configuration
if [ -d "$CONFIG_DIR" ]; then
    echo ""
    echo "Configuration directory found: $CONFIG_DIR"
    read -p "Do you want to remove configuration files? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Removing configuration..."
        rm -rf "$CONFIG_DIR"
        echo "Configuration removed"
    else
        echo "Configuration preserved"
    fi
fi

echo ""
echo "Uninstallation complete!"
echo ""
