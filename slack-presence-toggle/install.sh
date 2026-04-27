#!/usr/bin/env bash
# Install slack-presence-toggle: KWin script, desktop entry, autostart, config dir.
# KDE Plasma 6 / Wayland.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="slack-presence-toggle"
DISPLAY_NAME="Slack Presence Toggle"
CONFIG_DIR="$HOME/.config/$APP_NAME"
DESKTOP_FILE="$HOME/.local/share/applications/$APP_NAME.desktop"
AUTOSTART_FILE="$HOME/.config/autostart/$APP_NAME.desktop"

echo "Installing $APP_NAME from $PROJECT_ROOT"

# 1. KWin script
echo
echo "==> Installing KWin script"
"$PROJECT_ROOT/kwin-script/install.sh"

# 2. Make launcher executable
chmod +x "$PROJECT_ROOT/run.sh"

# 3. Desktop entry
echo
echo "==> Writing desktop entry: $DESKTOP_FILE"
mkdir -p "$(dirname "$DESKTOP_FILE")"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=$DISPLAY_NAME
Comment=Auto-toggle Slack presence based on Slack window focus
Exec=$PROJECT_ROOT/run.sh
Icon=user-online
StartupNotify=false
NoDisplay=false
Categories=Utility;Network;
X-KDE-StartupNotify=false
EOF

# 4. Autostart entry (same content)
echo "==> Writing autostart entry: $AUTOSTART_FILE"
mkdir -p "$(dirname "$AUTOSTART_FILE")"
cp "$DESKTOP_FILE" "$AUTOSTART_FILE"

# 5. Config dir
mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"

# 6. Token check
if [[ ! -f "$CONFIG_DIR/token" ]]; then
    cat <<EOF

==> Token file not found at $CONFIG_DIR/token

The app needs a User OAuth Token (xoxp-...) from a Slack app with these
User Token Scopes:
  - users:read
  - users:write
  - users.profile:read
  - users.profile:write

Setup:
  1. https://api.slack.com/apps -> Create New App -> From scratch
  2. OAuth & Permissions -> User Token Scopes -> add the four scopes above
  3. Install to Workspace -> approve
  4. Copy the User OAuth Token, then:
       ( umask 077 && cat > $CONFIG_DIR/token )
     # paste, Enter, Ctrl+D
       chmod 600 $CONFIG_DIR/token

The app will show a critical notification on startup if the token is
missing, invalid, or revoked.
EOF
fi

cat <<EOF

==> Installation complete

Start now:    $PROJECT_ROOT/run.sh
Or log out and back in for the autostart entry to fire.

Configuration: $CONFIG_DIR/config.toml (created on first run)
Token:         $CONFIG_DIR/token
Uninstall:     $PROJECT_ROOT/uninstall.sh
EOF
