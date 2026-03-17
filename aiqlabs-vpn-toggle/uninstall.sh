#!/bin/bash
set -e

rm -f ~/.local/share/applications/aiqlabs-vpn-toggle.desktop
update-desktop-database ~/.local/share/applications/ 2>/dev/null || true

echo "Removed aiqlabs-vpn-toggle.desktop from ~/.local/share/applications/"
