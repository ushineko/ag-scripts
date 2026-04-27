#!/usr/bin/env bash
# Install the slack-focus-monitor KWin script for the current user.
# KDE Plasma 6 / Wayland.

set -euo pipefail

SCRIPT_NAME="slack-focus-monitor"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="$HOME/.local/share/kwin/scripts/$SCRIPT_NAME"

echo "Installing to $TARGET_DIR"
mkdir -p "$TARGET_DIR"
cp "$SRC_DIR/metadata.json" "$TARGET_DIR/"
cp -r "$SRC_DIR/contents" "$TARGET_DIR/"

echo "Enabling in kwinrc"
kwriteconfig6 --file kwinrc --group Plugins --key "${SCRIPT_NAME}Enabled" true

echo "Reloading KWin"
qdbus6 org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true

# Force-reload via the Scripting interface — reconfigure alone does not always
# pick up newly-edited script bodies.
if qdbus6 org.kde.KWin /Scripting >/dev/null 2>&1; then
    qdbus6 org.kde.KWin /Scripting unloadScript "$SCRIPT_NAME" >/dev/null 2>&1 || true
    qdbus6 org.kde.KWin /Scripting loadScript "$TARGET_DIR/contents/code/main.js" "$SCRIPT_NAME" >/dev/null 2>&1 || true
    qdbus6 org.kde.KWin /Scripting start >/dev/null 2>&1 || true
fi

cat <<EOF

Installed. Verify the script is firing:
  journalctl --user -f | grep slack-focus-monitor

In another terminal, start the Python listener:
  python3 $(realpath --relative-to="$PWD" "$SRC_DIR/..")/focus_listener.py

If you don't see any output when alt-tabbing, log out and back in once to make
sure KWin actually picked up the new script, then re-run this install script.
EOF
