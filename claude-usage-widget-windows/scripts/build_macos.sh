#!/bin/bash
# Build "Claude Usage Widget.app" for macOS via PyInstaller.
#
# Produces dist/"Claude Usage Widget.app" — a tray/menu-bar agent app (no Dock
# icon). install.sh copies it into /Applications. Requires a framework build of
# Python (PyInstaller .app bundles do); the system python3 (/usr/bin/python3)
# qualifies, as does a Homebrew framework build.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "=== Building Claude Usage Widget.app for macOS ==="

# --- Dependency checks ---
if ! python3 -c "import PyInstaller" &>/dev/null; then
    echo "Error: PyInstaller not found. Install it with: pip3 install --user pyinstaller"
    echo "       (it is listed in requirements-dev.txt)"
    exit 1
fi
if ! python3 -c "import PySide6" &>/dev/null; then
    echo "Error: PySide6 not found. Install it with: pip3 install --user -r requirements.txt"
    exit 1
fi

# .app bundles require a framework build of Python. This is the single most
# common macOS PyInstaller failure, so fail loudly with a fix.
FRAMEWORK=$(python3 -c "import sysconfig; print(sysconfig.get_config_var('PYTHONFRAMEWORK') or '')")
if [ -z "$FRAMEWORK" ]; then
    echo "Error: this python3 is not a framework build; PyInstaller cannot make a .app."
    echo "       Use the system python3 (/usr/bin/python3) or a Homebrew framework"
    echo "       build (e.g. /opt/homebrew/bin/python3) to create the venv."
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
python3 -m PyInstaller --noconfirm --clean claude-usage-widget.spec

APP="dist/Claude Usage Widget.app"
if [ -d "$APP" ]; then
    echo ""
    echo "Build successful: $APP"
    echo "Test with:    open '$APP'"
    echo "Install with: ./install.sh   (copies it into /Applications)"
else
    echo "Build failed: $APP not produced."
    exit 1
fi
