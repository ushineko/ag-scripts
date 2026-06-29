#!/usr/bin/env bash
# Remove herdr-resurrect: disable the timer and remove the symlink + units.
# Leaves ~/.config/herdr-resurrect (config + snapshots) unless --purge.
set -euo pipefail

APP="herdr-resurrect"
BIN_DIR="$HOME/.local/bin"
UNIT_DIR="$HOME/.config/systemd/user"

if [[ "$OSTYPE" != "darwin"* ]]; then
    systemctl --user disable --now "$APP-save.timer" >/dev/null 2>&1 || true
    rm -f "$UNIT_DIR/$APP-save.timer" "$UNIT_DIR/$APP-save.service"
    systemctl --user daemon-reload 2>/dev/null || true
fi

rm -f "$BIN_DIR/$APP"

if [[ "${1:-}" == "--purge" ]]; then
    rm -rf "$HOME/.config/$APP"
    echo "removed config + snapshots (~/.config/$APP)"
fi

echo "$APP uninstalled."
