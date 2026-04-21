#!/bin/bash

# Configuration
APP_NAME="audio-source-switcher"
OLD_NAME="select-audio-source"
DESKTOP_FILE="$APP_NAME.desktop"
INSTALL_DIR="$HOME/.local/share/applications"
BIN_DIR="$HOME/.local/bin"
SCRIPT_PATH="$(cd "$(dirname "$0")" && pwd)/audio_source_switcher.py"
STATE_DIR="$HOME/.config/audio-source-switcher"
VOLKEY_MARKER="$STATE_DIR/volume-keys-bound"
VOLKEY_BACKUP="$STATE_DIR/volume-keys-backup.ini"

BIND_VOLUME_KEYS=0
for arg in "$@"; do
    case "$arg" in
        --bind-volume-keys) BIND_VOLUME_KEYS=1 ;;
        -h|--help)
            cat <<EOF
Usage: $0 [--bind-volume-keys]

  --bind-volume-keys   Release Plasma's default Increase/Decrease Volume
                       shortcuts (kmix) so a user-created custom shortcut
                       (System Settings -> Shortcuts) can bind 'Volume Up' /
                       'Volume Down' to '$APP_NAME --vol-up/--vol-down'.
                       Idempotent. Original values are backed up and
                       restored by 'uninstall.sh --unbind-volume-keys'
                       (or automatically on full uninstall).
EOF
            exit 0
            ;;
    esac
done

echo "Installing $APP_NAME..."

# 1. Remove old desktop file
if [ -f "$INSTALL_DIR/$OLD_NAME.desktop" ]; then
    echo "removing old desktop file: $INSTALL_DIR/$OLD_NAME.desktop"
    rm "$INSTALL_DIR/$OLD_NAME.desktop"
fi

# 2. Install new desktop file
if [ -f "./$DESKTOP_FILE" ]; then
    echo "Installing new desktop file to $INSTALL_DIR/$DESKTOP_FILE"
    cp "./$DESKTOP_FILE" "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/$DESKTOP_FILE"
else
    echo "Error: $DESKTOP_FILE not found in current directory!"
    exit 1
fi

# 3. Install autostart entry
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
echo "Installing autostart entry to $AUTOSTART_DIR/$DESKTOP_FILE"
cp "$INSTALL_DIR/$DESKTOP_FILE" "$AUTOSTART_DIR/"

# 4. Install CLI symlink in ~/.local/bin for shortcut/portable use
mkdir -p "$BIN_DIR"
chmod +x "$SCRIPT_PATH"
ln -sfn "$SCRIPT_PATH" "$BIN_DIR/$APP_NAME"
echo "Installed CLI symlink: $BIN_DIR/$APP_NAME -> $SCRIPT_PATH"

# 5. Update database
echo "Updating desktop database..."
update-desktop-database "$INSTALL_DIR"

# 6. Optionally release Plasma's default Volume Up/Down shortcuts so user
#    can bind them to our CLI via a custom shortcut. Idempotent: saves
#    original values once, then overwrites the active binding with 'none'.
if [ "$BIND_VOLUME_KEYS" = "1" ]; then
    if ! command -v kwriteconfig6 >/dev/null || ! command -v kreadconfig6 >/dev/null; then
        echo "Warning: kwriteconfig6/kreadconfig6 not found; skipping --bind-volume-keys (not a KDE session?)."
    else
        mkdir -p "$STATE_DIR"
        if [ ! -f "$VOLKEY_MARKER" ]; then
            # First-time bind: save current values before overwriting.
            : > "$VOLKEY_BACKUP"
            for key in increase_volume decrease_volume; do
                current=$(kreadconfig6 --file kglobalshortcutsrc --group kmix --key "$key")
                printf '%s=%s\n' "$key" "$current" >> "$VOLKEY_BACKUP"
            done
            touch "$VOLKEY_MARKER"
            echo "Saved original Volume Up/Down bindings to $VOLKEY_BACKUP"
        else
            echo "Volume keys already released (marker present); leaving backup intact."
        fi
        # Always ensure active binding is 'none' (idempotent).
        for key in increase_volume decrease_volume; do
            current=$(kreadconfig6 --file kglobalshortcutsrc --group kmix --key "$key")
            # ${current#*,} preserves the whole string when no comma is present.
            new="none,${current#*,}"
            if [ "$current" != "$new" ]; then
                kwriteconfig6 --file kglobalshortcutsrc --group kmix --key "$key" "$new"
                echo "Released kmix $key (was: $current)"
            fi
        done
        echo "Note: log out/in (or restart Plasma) so kglobalaccel picks up the change."
    fi
fi

echo "Done! You can now launch '$APP_NAME' from your application menu."
