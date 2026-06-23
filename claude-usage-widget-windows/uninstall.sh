#!/bin/bash
# Claude Usage Widget — macOS uninstaller.
#
# Unloads + removes the LaunchAgent, deletes the .app bundle, and (after a
# prompt) removes config and logs. Idempotent. Windows users: use
# uninstall.bat instead.
set -euo pipefail

APP_NAME="Claude Usage Widget"
LAUNCH_AGENT_LABEL="com.nverenin.claude-usage-widget"
CONFIG_DIR="$HOME/Library/Application Support/claude-usage-widget"
LOG_DIR="$HOME/Library/Logs/claude-usage-widget"

# --- Platform guard ---
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "uninstall.sh targets macOS only."
    echo "  - Windows: run uninstall.bat"
    exit 1
fi

LAUNCH_AGENT_PLIST="$HOME/Library/LaunchAgents/$LAUNCH_AGENT_LABEL.plist"
# The app may live in either Applications dir (install.sh picks whichever is
# writable); remove from both.
APP_LOCATIONS=("/Applications/$APP_NAME.app" "$HOME/Applications/$APP_NAME.app")

echo "Uninstalling Claude Usage Widget..."

# --- Unload + remove the LaunchAgent ---
if [ -f "$LAUNCH_AGENT_PLIST" ]; then
    launchctl bootout "gui/$(id -u)/$LAUNCH_AGENT_LABEL" 2>/dev/null || true
    rm -f "$LAUNCH_AGENT_PLIST"
    echo "  Removed LaunchAgent: $LAUNCH_AGENT_PLIST"
fi

# --- Stop any still-running instance launched from the bundle ---
if pkill -f "$APP_NAME.app/Contents/MacOS" 2>/dev/null; then
    echo "  Stopped running instance"
fi

# --- Remove the .app bundle from wherever it was installed ---
for app in "${APP_LOCATIONS[@]}"; do
    if [ -d "$app" ]; then
        rm -rf "$app"
        echo "  Removed app bundle: $app"
    fi
done

# --- Optionally remove config + logs ---
if [ -d "$CONFIG_DIR" ] || [ -d "$LOG_DIR" ]; then
    read -rp "Remove config and logs ($CONFIG_DIR, $LOG_DIR)? (y/N): " response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        rm -rf "$CONFIG_DIR" "$LOG_DIR"
        echo "  Removed config and logs."
    else
        echo "  Config and logs preserved."
    fi
fi

echo "Uninstallation complete."
