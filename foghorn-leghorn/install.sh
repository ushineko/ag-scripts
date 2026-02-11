#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="foghorn-leghorn"
INSTALL_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
MAIN_SCRIPT="$SCRIPT_DIR/foghorn_leghorn.py"

echo "Installing Foghorn Leghorn..."

# Check dependencies
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is required but not found."
    exit 1
fi

if ! python3 -c "import PyQt6" &>/dev/null; then
    echo "Error: PyQt6 is required. Install it with: pip install PyQt6"
    exit 1
fi

# Create directories
mkdir -p "$INSTALL_DIR"
mkdir -p "$DESKTOP_DIR"

# Make script executable
chmod +x "$MAIN_SCRIPT"

# Create symlink
ln -sf "$MAIN_SCRIPT" "$INSTALL_DIR/$APP_NAME"
echo "  Symlink: $INSTALL_DIR/$APP_NAME -> $MAIN_SCRIPT"

# Install desktop entry
cp "$SCRIPT_DIR/$APP_NAME.desktop" "$DESKTOP_DIR/$APP_NAME.desktop"
echo "  Desktop entry: $DESKTOP_DIR/$APP_NAME.desktop"

# Update desktop database
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

echo "Installation complete!"
echo "Run with: $APP_NAME"
