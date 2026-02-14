#!/usr/bin/env bash
#
# Installation script for VPN Toggle v3.2
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons"

echo "Installing VPN Toggle v3.2..."

# Check dependencies
echo "Checking dependencies..."

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is required but not found"
    exit 1
fi

# Check NetworkManager (nmcli)
if ! command -v nmcli &> /dev/null; then
    echo "Error: NetworkManager (nmcli) is required but not found"
    echo "Please install NetworkManager first"
    exit 1
fi

# Check PyQt6
if ! python3 -c "import PyQt6" &> /dev/null; then
    echo "Warning: PyQt6 not found"
    echo "Installing PyQt6..."
    pip install --user PyQt6 requests || {
        echo "Failed to install PyQt6. Please install manually:"
        echo "  pip install --user PyQt6 requests"
        exit 1
    }
fi

# Check pyqtgraph (required for metrics dashboard)
if ! python3 -c "import pyqtgraph" &> /dev/null; then
    echo "Warning: pyqtgraph not found"
    echo "Installing pyqtgraph..."
    pip install --user pyqtgraph || {
        echo "Failed to install pyqtgraph. Please install manually:"
        echo "  pip install --user pyqtgraph"
        exit 1
    }
fi

# Create install directory if it doesn't exist
mkdir -p "$INSTALL_DIR"

# Create symlink to main script
echo "Installing vpn-toggle-v2..."
ln -sf "$SCRIPT_DIR/vpn_toggle_v2.py" "$INSTALL_DIR/vpn-toggle-v2"

# Make sure it's executable
chmod +x "$SCRIPT_DIR/vpn_toggle_v2.py"

# Install icon
echo "Installing icon..."
mkdir -p "$ICON_DIR"
cp "$SCRIPT_DIR/vpn_toggle/icon.svg" "$ICON_DIR/vpn-toggle-v2.svg"

# Create desktop file
echo "Creating desktop launcher..."
mkdir -p "$DESKTOP_DIR"

cat > "$DESKTOP_DIR/vpn-toggle-v2.desktop" << EOF
[Desktop Entry]
Type=Application
Name=VPN Toggle v3.2
Comment=VPN Manager with integrated monitoring
Exec=$INSTALL_DIR/vpn-toggle-v2
Icon=$ICON_DIR/vpn-toggle-v2.svg
Terminal=false
Categories=Network;System;
Keywords=vpn;network;monitor;
EOF

# Update desktop database if available
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

echo ""
echo "Installation complete!"
echo ""
echo "You can now run VPN Toggle v3.2 by:"
echo "  1. Running: vpn-toggle-v2"
echo "  2. Searching for 'VPN Toggle' in your application launcher"
echo ""
echo "Note: Make sure $INSTALL_DIR is in your PATH"
echo "      You may need to log out and back in for the changes to take effect"
echo ""
