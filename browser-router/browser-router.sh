#!/bin/bash
# browser-router.sh - Routes URLs to different browsers based on domain patterns
#
# Created: 2026-02-02
# Purpose: Chromium/Vivaldi lack PipeWire camera support on Wayland, so routes
#          webcam-dependent sites (Teams, etc.) to Firefox while keeping Vivaldi
#          as the default browser for everything else.
#
# Usage: browser-router.sh <url>
#
# Configuration: Edit the domain patterns in the if statement below to customize
#                which URLs go to Firefox vs Vivaldi.

set -euo pipefail

url="${1:-}"

if [[ -z "$url" ]]; then
    echo "Usage: browser-router.sh <url>" >&2
    exit 1
fi

# Route webcam-dependent sites to Firefox (PipeWire camera support works there)
if [[ "$url" == *"teams.microsoft.com"* ]] || [[ "$url" == *"teams.live.com"* ]]; then
    exec firefox "$url"
else
    exec vivaldi-stable "$url"
fi
