#!/usr/bin/env bash
# Install Ryujinx HiDPI launcher

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HOME/.local/share/applications/ryujinx-bigfont.desktop"

cp "$SCRIPT_DIR/ryujinx-bigfont.desktop" "$DEST"
update-desktop-database "$HOME/.local/share/applications/" 2>/dev/null || true

echo "Installed: $DEST"
echo "Launch 'Ryujinx (Big Font)' from your app menu."
