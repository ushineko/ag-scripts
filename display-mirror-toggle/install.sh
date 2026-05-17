#!/usr/bin/env bash
# Install display-mirror-toggle utility (CLI + tray)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="display-mirror-toggle"
DESKTOP_FILE="${APP_NAME}.desktop"

CLI_SCRIPT="${SCRIPT_DIR}/${APP_NAME}.sh"
TRAY_SCRIPT="${SCRIPT_DIR}/display-mirror-tray.py"

BIN_DIR="${HOME}/bin"
LOCAL_BIN_DIR="${HOME}/.local/bin"
APPS_DIR="${HOME}/.local/share/applications"
AUTOSTART_DIR="${HOME}/.config/autostart"

echo "Installing ${APP_NAME}..."

# 1. CLI symlink (existing behavior).
chmod +x "${CLI_SCRIPT}"
mkdir -p "${BIN_DIR}"
ln -sfn "${CLI_SCRIPT}" "${BIN_DIR}/${APP_NAME}"
echo "  Installed CLI: ${BIN_DIR}/${APP_NAME}"

# 2. Tray entry script + symlink for terminal invocation.
chmod +x "${TRAY_SCRIPT}"
mkdir -p "${LOCAL_BIN_DIR}"
ln -sfn "${TRAY_SCRIPT}" "${LOCAL_BIN_DIR}/display-mirror-tray"
echo "  Installed tray launcher: ${LOCAL_BIN_DIR}/display-mirror-tray"

# 3. .desktop entry — rewrite Exec line to point at the checkout.
mkdir -p "${APPS_DIR}"
INSTALLED_DESKTOP="${APPS_DIR}/${DESKTOP_FILE}"
sed -E "s|^Exec=.*|Exec=/usr/bin/python3 ${TRAY_SCRIPT}|" \
    "${SCRIPT_DIR}/${DESKTOP_FILE}" > "${INSTALLED_DESKTOP}"
chmod 644 "${INSTALLED_DESKTOP}"
echo "  Installed desktop entry: ${INSTALLED_DESKTOP}"

# 4. Autostart entry — same content as the applications entry.
mkdir -p "${AUTOSTART_DIR}"
cp "${INSTALLED_DESKTOP}" "${AUTOSTART_DIR}/${DESKTOP_FILE}"
echo "  Installed autostart entry: ${AUTOSTART_DIR}/${DESKTOP_FILE}"

# 5. Refresh desktop database (non-fatal if not installed).
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${APPS_DIR}" >/dev/null 2>&1 || true
fi

if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo ""
    echo "NOTE: ${BIN_DIR} is not in your PATH."
    echo "Add this to your shell profile:"
    echo "  export PATH=\"\$HOME/bin:\$PATH\""
fi

cat <<EOF

Done.

  CLI:        ${BIN_DIR}/${APP_NAME}            (display-mirror-toggle --help)
  Tray:       ${LOCAL_BIN_DIR}/display-mirror-tray
  Autostart:  enabled (tray launches at login)

Launch the tray now with:
  display-mirror-tray
EOF
