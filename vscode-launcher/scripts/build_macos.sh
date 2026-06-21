#!/bin/bash
# Build vscode-launcher.app for macOS via PyInstaller.
#
# Produces dist/vscode-launcher.app — a menu-bar agent app (no Dock icon).
# install.sh copies it into /Applications. Requires a framework build of
# Python (PyInstaller .app bundles do); the system CommandLineTools python3
# qualifies, as does Homebrew's.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "=== Building vscode-launcher.app for macOS ==="

# --- Dependency checks ---
if ! python3 -c "import PyInstaller" &>/dev/null; then
    echo "Error: PyInstaller not found. Install it with: pip3 install --user pyinstaller"
    exit 1
fi
if ! python3 -c "import PyQt6" &>/dev/null; then
    echo "Error: PyQt6 not found. Install it with: pip3 install --user PyQt6"
    exit 1
fi

# .app bundles require a framework build of Python.
FRAMEWORK=$(python3 -c "import sysconfig; print(sysconfig.get_config_var('PYTHONFRAMEWORK') or '')")
if [ -z "$FRAMEWORK" ]; then
    echo "Error: this python3 is not a framework build; PyInstaller cannot make a .app."
    echo "       Use the system python3 (/usr/bin/python3) or a Homebrew framework build."
    exit 1
fi
echo "Python: $(python3 --version) (framework: $FRAMEWORK)"

# --- Regenerate the .icns from the SVG ---
echo "Generating app icon..."
QT_QPA_PLATFORM=offscreen python3 scripts/create_icns.py

# --- Build ---
echo "Cleaning previous build..."
rm -rf build dist

echo "Running PyInstaller..."
python3 -m PyInstaller --noconfirm --clean vscode-launcher.spec

APP="dist/vscode-launcher.app"
if [ -d "$APP" ]; then
    echo ""
    echo "Build successful: $APP"
    echo "Test with:  open '$APP'"
    echo "Install with: ./install.sh   (copies it into /Applications)"
else
    echo "Build failed: $APP not produced."
    exit 1
fi
