#!/usr/bin/env bash
# Uninstall display-mirror-toggle utility (CLI + tray)

set -euo pipefail

APP_NAME="display-mirror-toggle"
DESKTOP_FILE="${APP_NAME}.desktop"

BIN_DIR="${HOME}/bin"
LOCAL_BIN_DIR="${HOME}/.local/bin"
APPS_DIR="${HOME}/.local/share/applications"
AUTOSTART_DIR="${HOME}/.config/autostart"

PURGE_CONFIG=0
for arg in "$@"; do
    case "$arg" in
        --purge-config) PURGE_CONFIG=1 ;;
        -h|--help)
            cat <<EOF
Usage: $0 [--purge-config]

  --purge-config   Also remove ~/.config/${APP_NAME}/ (config + saved
                   source/replica/hotkey).
EOF
            exit 0
            ;;
    esac
done

echo "Uninstalling ${APP_NAME}..."

remove_if_present() {
    local path="$1"
    if [[ -L "$path" || -e "$path" ]]; then
        rm -f "$path"
        echo "  Removed: $path"
    fi
}

# 1. Stop the tray if it's running so we don't leave a zombie icon.
if pgrep -f "display-mirror-tray(\.py)?" >/dev/null 2>&1; then
    echo "  Stopping running tray instance..."
    pkill -f "display-mirror-tray(\.py)?" || true
fi

remove_if_present "${BIN_DIR}/${APP_NAME}"
remove_if_present "${LOCAL_BIN_DIR}/display-mirror-tray"
remove_if_present "${APPS_DIR}/${DESKTOP_FILE}"
remove_if_present "${AUTOSTART_DIR}/${DESKTOP_FILE}"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${APPS_DIR}" >/dev/null 2>&1 || true
fi

if [[ "$PURGE_CONFIG" == "1" ]]; then
    CONFIG_DIR="${HOME}/.config/${APP_NAME}"
    if [[ -d "$CONFIG_DIR" ]]; then
        rm -rf "$CONFIG_DIR"
        echo "  Removed config dir: $CONFIG_DIR"
    fi
fi

echo "Done."
