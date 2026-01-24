#!/bin/bash

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WRAPPER_SCRIPT="$SCRIPT_DIR/qbittorrent_vpn_wrapper.py"
DESKTOP_FILE="$SCRIPT_DIR/qbittorrent-secure.desktop"
INSTALL_DIR="$HOME/.local/share/applications"

echo "--- Installing qBittorrent VPN Wrapper ---"

# 1. Make the wrapper script executable
if [ -f "$WRAPPER_SCRIPT" ]; then
    chmod +x "$WRAPPER_SCRIPT"
    echo "✓ Made wrapper script executable: $WRAPPER_SCRIPT"
else
    echo "❌ Error: Wrapper script not found at $WRAPPER_SCRIPT"
    exit 1
fi

# 2. Install Desktop File
if [ -f "$DESKTOP_FILE" ]; then
    # Ensure install directory exists
    mkdir -p "$INSTALL_DIR"
    
    # Copy file
    cp "$DESKTOP_FILE" "$INSTALL_DIR/"
    
    # Update execution permissions just in case
    chmod +x "$INSTALL_DIR/qbittorrent-secure.desktop"
    
    echo "✓ Installed desktop entry to: $INSTALL_DIR/qbittorrent-secure.desktop"
else
    echo "❌ Error: Desktop file not found at $DESKTOP_FILE"
    exit 1
fi

# 3. Refresh desktop database
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$INSTALL_DIR"
    echo "✓ Desktop database updated."
else
    echo "ℹ update-desktop-database not found, you may need to relogin or refresh KDE to see the icon."
fi

echo "--- Installation Complete ---"
echo "You should now see 'qBittorrent Secure VPN' in your application launcher."
