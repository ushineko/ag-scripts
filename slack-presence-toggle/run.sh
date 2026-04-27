#!/usr/bin/env bash
# Launcher for slack-presence-toggle. Used by the desktop entry / autostart.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
exec python3 -m slack_presence_toggle "$@"
