#!/usr/bin/env bash
# Remove Ryujinx HiDPI launcher

set -euo pipefail

DEST="$HOME/.local/share/applications/ryujinx-bigfont.desktop"

if [[ -f "$DEST" ]]; then
    rm "$DEST"
    update-desktop-database "$HOME/.local/share/applications/" 2>/dev/null || true
    echo "Removed: $DEST"
else
    echo "Not installed."
fi
