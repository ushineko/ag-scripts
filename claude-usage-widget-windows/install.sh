#!/bin/bash
# Claude Usage Widget — macOS installer.
#
# Builds the PyInstaller .app bundle, installs it to /Applications (or
# ~/Applications), and registers a LaunchAgent so the tray widget starts at
# login. Windows users: use install.bat instead (run-from-source).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="Claude Usage Widget"
EXE_NAME="claude-usage-widget"
LAUNCH_AGENT_LABEL="com.nverenin.claude-usage-widget"

# --- Platform guard ---
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "install.sh targets macOS only."
    echo "  - Windows: run install.bat"
    echo "  - Linux/other: run from source with 'python -m src.main'"
    exit 1
fi

BUILT_APP="$SCRIPT_DIR/dist/$APP_NAME.app"
LAUNCH_AGENT_DIR="$HOME/Library/LaunchAgents"
LAUNCH_AGENT_PLIST="$LAUNCH_AGENT_DIR/$LAUNCH_AGENT_LABEL.plist"

# Prefer /Applications (Spotlight + Finder visible); fall back to
# ~/Applications when /Applications isn't writable without admin.
if [ -w /Applications ] || [ ! -e /Applications ]; then
    APPLICATIONS_DIR="/Applications"
else
    APPLICATIONS_DIR="$HOME/Applications"
fi
INSTALLED_APP="$APPLICATIONS_DIR/$APP_NAME.app"
APP_BIN="$INSTALLED_APP/Contents/MacOS/$EXE_NAME"

echo "Installing Claude Usage Widget..."

# --- Dependencies ---
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is required but not found."
    exit 1
fi

# --- Build the .app on demand if not already built ---
if [ ! -d "$BUILT_APP" ]; then
    echo "  No built app found; building it (scripts/build_macos.sh)..."
    "$SCRIPT_DIR/scripts/build_macos.sh"
fi
if [ ! -d "$BUILT_APP" ]; then
    echo "Error: build did not produce $BUILT_APP." >&2
    exit 1
fi

# --- Install the bundle ---
mkdir -p "$APPLICATIONS_DIR"
rm -rf "$INSTALLED_APP"
cp -R "$BUILT_APP" "$INSTALLED_APP"
echo "  App: $INSTALLED_APP"

# --- LaunchAgent (autostart the tray widget at login) ---
# No PATH override is needed: the widget is self-contained inside the bundle
# and shells out to nothing, so launchd's minimal default PATH is fine.
mkdir -p "$LAUNCH_AGENT_DIR"
cat > "$LAUNCH_AGENT_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LAUNCH_AGENT_LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$APP_BIN</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>ProcessType</key>
    <string>Interactive</string>
</dict>
</plist>
EOF
echo "  LaunchAgent: $LAUNCH_AGENT_PLIST"

# Reload so the running definition matches what we just wrote. bootout is
# best-effort (no-op if not loaded); bootstrap loads it — making re-install
# idempotent.
GUI_TARGET="gui/$(id -u)"
launchctl bootout "$GUI_TARGET/$LAUNCH_AGENT_LABEL" 2>/dev/null || true
if launchctl bootstrap "$GUI_TARGET" "$LAUNCH_AGENT_PLIST" 2>/dev/null; then
    echo "  Loaded LaunchAgent (tray widget starts now and on each login)."
else
    echo "  (Could not auto-load the LaunchAgent. It will start on next login,"
    echo "   or start it now with: open '$INSTALLED_APP')"
fi

echo ""
echo "Installation complete!"
echo ""
echo "First launch (unsigned app): if macOS Gatekeeper blocks it, right-click"
echo "the app in Finder and choose Open, then confirm — once only."
echo "Look for the gauge icon in the menu bar; left-click it to show the widget."
