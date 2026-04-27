#!/usr/bin/env bash
# Uninstall slack-presence-toggle. Stops the running app first so it
# releases any forced presence/status state cleanly.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="slack-presence-toggle"
CONFIG_DIR="$HOME/.config/$APP_NAME"
DESKTOP_FILE="$HOME/.local/share/applications/$APP_NAME.desktop"
AUTOSTART_FILE="$HOME/.config/autostart/$APP_NAME.desktop"

echo "Uninstalling $APP_NAME"

# 1. Stop running app (lets it call its shutdown sequence to release any
#    forced presence/status before we yank everything else).
if pgrep -f "python3.*slack_presence_toggle" >/dev/null 2>&1; then
    echo
    echo "==> Stopping running app (gracefully)"
    pkill -TERM -f "python3.*slack_presence_toggle" || true
    # Give it up to 5s to hit Slack and clear forced state.
    for i in 1 2 3 4 5; do
        sleep 1
        if ! pgrep -f "python3.*slack_presence_toggle" >/dev/null 2>&1; then
            break
        fi
    done
    if pgrep -f "python3.*slack_presence_toggle" >/dev/null 2>&1; then
        echo "    still running after 5s; sending SIGKILL"
        pkill -KILL -f "python3.*slack_presence_toggle" 2>/dev/null || true
    fi
fi

# 2. KWin script
echo
echo "==> Removing KWin script"
"$PROJECT_ROOT/kwin-script/uninstall.sh"

# 3. Desktop entry + autostart
echo
echo "==> Removing desktop entries"
rm -f "$DESKTOP_FILE"
rm -f "$AUTOSTART_FILE"

# 4. Config dir + token (with confirmation)
if [[ -d "$CONFIG_DIR" ]]; then
    echo
    echo "==> Config directory $CONFIG_DIR exists."
    echo "    Contents:"
    ls -la "$CONFIG_DIR" | sed 's/^/      /'
    echo
    read -r -p "Remove config dir (includes token file)? [y/N] " yn
    if [[ "$yn" =~ ^[Yy]$ ]]; then
        rm -rf "$CONFIG_DIR"
        echo "    removed $CONFIG_DIR"
        echo
        echo "    NOTE: the token may still be valid in Slack until you revoke it."
        echo "    To revoke: Slack app config > OAuth & Permissions, or via API:"
        echo "      curl -X POST -H 'Authorization: Bearer xoxp-...' https://slack.com/api/auth.revoke"
    else
        echo "    kept $CONFIG_DIR"
    fi
fi

echo
echo "Done."
