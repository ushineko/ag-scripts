#!/bin/bash

# Configuration
APP_NAME="audio-source-switcher"
INSTALL_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$APP_NAME.desktop"
BIN_DIR="$HOME/.local/bin"
STATE_DIR="$HOME/.config/audio-source-switcher"
VOLKEY_MARKER="$STATE_DIR/volume-keys-bound"
VOLKEY_BACKUP="$STATE_DIR/volume-keys-backup.ini"

UNBIND_ONLY=0
for arg in "$@"; do
    case "$arg" in
        --unbind-volume-keys) UNBIND_ONLY=1 ;;
        -h|--help)
            cat <<EOF
Usage: $0 [--unbind-volume-keys]

  (no args)              Full uninstall. Also restores Plasma Volume Up/Down
                         defaults if they were released by install.sh.
  --unbind-volume-keys   Restore Plasma Volume Up/Down shortcuts only;
                         leave the app installed.
EOF
            exit 0
            ;;
    esac
done

restore_volume_keys() {
    if [ ! -f "$VOLKEY_MARKER" ]; then
        echo "Volume keys were not released by install.sh; nothing to restore."
        return
    fi
    if ! command -v kwriteconfig6 >/dev/null; then
        echo "Warning: kwriteconfig6 not found; cannot restore bindings."
        return
    fi
    if [ -f "$VOLKEY_BACKUP" ]; then
        while IFS='=' read -r key value; do
            [ -z "$key" ] && continue
            kwriteconfig6 --file kglobalshortcutsrc --group kmix --key "$key" "$value"
            echo "Restored kmix $key -> $value"
        done < "$VOLKEY_BACKUP"
        rm -f "$VOLKEY_BACKUP"
    fi
    rm -f "$VOLKEY_MARKER"
    rmdir "$STATE_DIR" 2>/dev/null || true
    echo "Note: log out/in (or restart Plasma) so kglobalaccel picks up the change."
}

if [ "$UNBIND_ONLY" = "1" ]; then
    echo "Restoring Plasma volume key bindings..."
    restore_volume_keys
    exit 0
fi

echo "Uninstalling $APP_NAME..."

if [ -f "$INSTALL_DIR/$DESKTOP_FILE" ]; then
    rm "$INSTALL_DIR/$DESKTOP_FILE"
    echo "Removed $INSTALL_DIR/$DESKTOP_FILE"
else
    echo "Desktop file not found at $INSTALL_DIR/$DESKTOP_FILE"
fi

AUTOSTART_DIR="$HOME/.config/autostart"
if [ -f "$AUTOSTART_DIR/$DESKTOP_FILE" ]; then
    rm "$AUTOSTART_DIR/$DESKTOP_FILE"
    echo "Removed autostart entry $AUTOSTART_DIR/$DESKTOP_FILE"
fi

if [ -L "$BIN_DIR/$APP_NAME" ] || [ -f "$BIN_DIR/$APP_NAME" ]; then
    rm -f "$BIN_DIR/$APP_NAME"
    echo "Removed CLI symlink $BIN_DIR/$APP_NAME"
fi

echo "Updating desktop database..."
update-desktop-database "$INSTALL_DIR"

restore_volume_keys

echo "Uninstallation complete."
