#!/bin/bash
set -e

rm -f ~/.local/share/applications/facecam-toggle.desktop
update-desktop-database ~/.local/share/applications/ 2>/dev/null || true

echo "Removed facecam-toggle.desktop"
