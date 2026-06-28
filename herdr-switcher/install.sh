#!/usr/bin/env bash
# Install herdr-switcher: symlink the daemon + CLI, install the desktop entry,
# autostart entry, and icon, then (re)start the daemon. KDE Plasma 6 / Wayland.
# macOS is not yet supported (see specs/001 non-goals).
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="herdr-switcher"

if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "herdr-switcher: macOS is not yet supported (KDE/Wayland only in v1)."
    echo "See specs/001-herdr-switcher-alt-tab-space-switcher.md (Non-goals)."
    exit 1
fi

# --- dependency checks ------------------------------------------------------
missing=()
command -v python3 >/dev/null 2>&1 || missing+=("python3")
python3 -c "import PyQt6.QtWidgets, PyQt6.QtDBus" 2>/dev/null || missing+=("python-pyqt6")
command -v herdr   >/dev/null 2>&1 || missing+=("herdr")
command -v kdotool >/dev/null 2>&1 || missing+=("kdotool")
command -v qdbus6  >/dev/null 2>&1 || missing+=("qdbus6 (qt6-tools)")
if (( ${#missing[@]} )); then
    echo "herdr-switcher: missing dependencies: ${missing[*]}"
    echo "Install them and re-run. (Arch: pacman -S python-pyqt6 qt6-tools; herdr/kdotool via their own installers.)"
    exit 1
fi

BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
AUTOSTART_DIR="$HOME/.config/autostart"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
mkdir -p "$BIN_DIR" "$APP_DIR" "$AUTOSTART_DIR" "$ICON_DIR"

# --- symlinks ---------------------------------------------------------------
ln -sf "$SRC_DIR/herdr_switcher.py" "$BIN_DIR/$APP"
ln -sf "$SRC_DIR/cli.py" "$BIN_DIR/$APP-cli"
chmod +x "$SRC_DIR/herdr_switcher.py" "$SRC_DIR/cli.py"
echo "symlinked $BIN_DIR/$APP and $BIN_DIR/$APP-cli"

# --- icon -------------------------------------------------------------------
install -m 644 "$SRC_DIR/$APP.svg" "$ICON_DIR/$APP.svg"

# --- desktop entry (also fixes the xdg-portal app-id warning) ---------------
cat > "$APP_DIR/$APP.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=herdr-switcher
Comment=Alt-tab popup to switch between herdr spaces
Exec=$BIN_DIR/$APP --tray
Icon=$APP
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
StartupNotify=false
EOF
echo "installed desktop entry"

# --- autostart --------------------------------------------------------------
cp "$APP_DIR/$APP.desktop" "$AUTOSTART_DIR/$APP.desktop"
echo "installed autostart entry"

# --- refresh caches (best-effort) -------------------------------------------
command -v kbuildsycoca6 >/dev/null 2>&1 && kbuildsycoca6 >/dev/null 2>&1 || true
command -v gtk-update-icon-cache >/dev/null 2>&1 \
    && gtk-update-icon-cache -q -t -f "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

# --- (re)start the daemon ---------------------------------------------------
# Match the actual daemon invocation (… --tray), not incidental mentions of the
# path, so this never kills the installing shell or an unrelated process.
pkill -f "herdr_switcher.py --tray" 2>/dev/null || true
pkill -f "$BIN_DIR/$APP --tray" 2>/dev/null || true
sleep 0.5
# Launch detached, with herdr's recursion-guard vars stripped so the daemon is
# never treated as a nested herdr if installed from inside a herdr shell.
env -u HERDR_ENV -u HERDR_SESSION -u CLAUDECODE \
    setsid "$BIN_DIR/$APP" --tray >/dev/null 2>&1 < /dev/null &
disown 2>/dev/null || true

echo
echo "herdr-switcher installed and started."
echo "  Hotkey: Shift+Tab (configurable in ~/.config/herdr-switcher/config.json)"
echo "  CLI:    $APP-cli list | current | switch <session> <workspace_id>"
echo "  Autostarts on next login."
