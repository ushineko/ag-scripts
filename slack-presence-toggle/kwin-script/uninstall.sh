#!/usr/bin/env bash
# Remove the slack-focus-monitor KWin script.

set -euo pipefail

SCRIPT_NAME="slack-focus-monitor"
TARGET_DIR="$HOME/.local/share/kwin/scripts/$SCRIPT_NAME"

echo "Disabling in kwinrc"
kwriteconfig6 --file kwinrc --group Plugins --key "${SCRIPT_NAME}Enabled" false

if qdbus6 org.kde.KWin /Scripting >/dev/null 2>&1; then
    qdbus6 org.kde.KWin /Scripting unloadScript "$SCRIPT_NAME" >/dev/null 2>&1 || true
fi

if [[ -d "$TARGET_DIR" ]]; then
    echo "Removing $TARGET_DIR"
    rm -rf "$TARGET_DIR"
fi

echo "Reloading KWin"
qdbus6 org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true

echo "Done."
