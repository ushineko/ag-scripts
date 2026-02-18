#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="dhcp-lease-monitor"
MAIN_SCRIPT="$SCRIPT_DIR/dhcp-lease-monitor.py"
DESKTOP_TEMPLATE="$SCRIPT_DIR/dhcp-lease-monitor.desktop"
AUTOSTART_DIR="$HOME/.config/autostart"
LOCAL_APPS_DIR="$HOME/.local/share/applications"

echo "Installing DHCP Lease Monitor..."

if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 is required."
    exit 1
fi

if ! python3 -c "import PyQt6, structlog" >/dev/null 2>&1; then
    echo "Error: missing dependencies. Install PyQt6 and structlog first."
    exit 1
fi

if ! python3 -c "import inotify_simple, mac_vendor_lookup" >/dev/null 2>&1; then
    echo "Warning: inotify_simple and/or mac-vendor-lookup not installed."
    echo "The app still runs, but realtime updates/vendor detection may be limited."
fi

chmod +x "$MAIN_SCRIPT" "$SCRIPT_DIR/uninstall.sh"

rendered_desktop="$(mktemp)"
trap 'rm -f "$rendered_desktop"' EXIT
sed "s|REPLACE_WITH_SCRIPT_PATH|$MAIN_SCRIPT|g" "$DESKTOP_TEMPLATE" > "$rendered_desktop"

echo "Where should the desktop entry be installed?"
echo "1) Autostart (launch on login)"
echo "2) Applications menu"
echo "3) Both"
read -r -p "Select [1-3]: " choice

case "$choice" in
    1)
        mkdir -p "$AUTOSTART_DIR"
        cp "$rendered_desktop" "$AUTOSTART_DIR/$APP_NAME.desktop"
        echo "Installed to $AUTOSTART_DIR"
        ;;
    2)
        mkdir -p "$LOCAL_APPS_DIR"
        cp "$rendered_desktop" "$LOCAL_APPS_DIR/$APP_NAME.desktop"
        echo "Installed to $LOCAL_APPS_DIR"
        ;;
    3)
        mkdir -p "$AUTOSTART_DIR" "$LOCAL_APPS_DIR"
        cp "$rendered_desktop" "$AUTOSTART_DIR/$APP_NAME.desktop"
        cp "$rendered_desktop" "$LOCAL_APPS_DIR/$APP_NAME.desktop"
        echo "Installed to autostart + applications menu"
        ;;
    *)
        echo "Invalid selection."
        exit 1
        ;;
esac

update-desktop-database "$LOCAL_APPS_DIR" >/dev/null 2>&1 || true

if [[ "${XDG_SESSION_DESKTOP:-}" == "KDE" || "${DESKTOP_SESSION:-}" == "plasma" ]]; then
    echo "Detected KDE Plasma. Installing KWin always-on-top rule..."
    python3 "$SCRIPT_DIR/install_kwin_rule.py" || echo "Warning: KWin rule installation failed."
fi

echo "Installation complete."
echo "Run with: python3 $MAIN_SCRIPT"
