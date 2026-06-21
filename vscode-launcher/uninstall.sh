#!/bin/bash
set -euo pipefail

APP_NAME="vscode-launcher"
LOOKUP_NAME="vscl-tmux-lookup"
CONFIG_DIR="$HOME/.config/vscode-launcher"
ZSHRC="$HOME/.zshrc"

BEGIN_MARKER="# --- vscode-launcher tmux hook (BEGIN) ---"
END_MARKER="# --- vscode-launcher tmux hook (END) ---"

# --- Platform detection (mirror install.sh) ---
if [[ "$OSTYPE" == "darwin"* ]]; then
    IS_MACOS=1
    INSTALL_DIR="/usr/local/bin"
    LAUNCH_AGENT_LABEL="com.vscode-launcher.agent"
    LAUNCH_AGENT_PLIST="$HOME/Library/LaunchAgents/$LAUNCH_AGENT_LABEL.plist"
    # The app may live in either Applications dir (install.sh picks whichever
    # is writable); remove from both.
    APP_LOCATIONS=("/Applications/vscode-launcher.app" "$HOME/Applications/vscode-launcher.app")
else
    IS_MACOS=0
    INSTALL_DIR="$HOME/.local/bin"
    DESKTOP_DIR="$HOME/.local/share/applications"
    AUTOSTART_DIR="$HOME/.config/autostart"
    ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
fi

echo "Uninstalling VSCode Launcher..."

# --- Stop any running instance (shared) ---
# Two invocation forms to catch: a direct `python vscode_launcher.py` run,
# and the installed symlink (`$INSTALL_DIR/vscode-launcher --tray`, used by
# the macOS LaunchAgent and the Linux autostart entry). When launched via
# the symlink the cmdline shows the symlink path, not "vscode_launcher.py",
# so matching only the script name would miss the resident daemon.
# (On macOS the LaunchAgent is also stopped below via `launchctl bootout`.)
if pkill -f vscode_launcher.py 2>/dev/null \
    || pkill -f "$INSTALL_DIR/$APP_NAME" 2>/dev/null \
    || pkill -f "vscode-launcher.app/Contents/MacOS" 2>/dev/null; then
    echo "  Stopped running instances"
fi

# --- Remove symlinks (shared) ---
if [ -L "$INSTALL_DIR/$APP_NAME" ]; then
    rm "$INSTALL_DIR/$APP_NAME"
    echo "  Removed symlink: $INSTALL_DIR/$APP_NAME"
fi

if [ -L "$INSTALL_DIR/$LOOKUP_NAME" ]; then
    rm "$INSTALL_DIR/$LOOKUP_NAME"
    echo "  Removed symlink: $INSTALL_DIR/$LOOKUP_NAME"
fi

if [[ "$IS_MACOS" -eq 1 ]]; then
    # --- macOS: unload + remove the LaunchAgent ---
    if [ -f "$LAUNCH_AGENT_PLIST" ]; then
        launchctl bootout "gui/$(id -u)/$LAUNCH_AGENT_LABEL" 2>/dev/null || true
        rm -f "$LAUNCH_AGENT_PLIST"
        echo "  Removed LaunchAgent: $LAUNCH_AGENT_PLIST"
    fi
    # --- macOS: remove the .app bundle from wherever it was installed ---
    for app in "${APP_LOCATIONS[@]}"; do
        if [ -d "$app" ]; then
            rm -rf "$app"
            echo "  Removed app bundle: $app"
        fi
    done
else
    # --- Linux: remove .desktop entries + icon, refresh caches ---
    if [ -f "$DESKTOP_DIR/$APP_NAME.desktop" ]; then
        rm "$DESKTOP_DIR/$APP_NAME.desktop"
        echo "  Removed desktop entry: $DESKTOP_DIR/$APP_NAME.desktop"
    fi
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

    if [ -f "$AUTOSTART_DIR/$APP_NAME.desktop" ]; then
        rm "$AUTOSTART_DIR/$APP_NAME.desktop"
        echo "  Removed autostart entry: $AUTOSTART_DIR/$APP_NAME.desktop"
    fi

    if [ -f "$ICON_DIR/$APP_NAME.svg" ]; then
        rm "$ICON_DIR/$APP_NAME.svg"
        echo "  Removed icon: $ICON_DIR/$APP_NAME.svg"
        gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
    fi

    # Rebuild KDE sycoca so KRunner / app menu drop the cached entry immediately.
    kbuildsycoca6 --noincremental 2>/dev/null || kbuildsycoca5 --noincremental 2>/dev/null || true
fi

# --- Remove zsh hook block (inclusive, shared) ---
if [ -f "$ZSHRC" ] && grep -Fq "$BEGIN_MARKER" "$ZSHRC"; then
    cp "$ZSHRC" "$ZSHRC.vscode-launcher.bak"
    # install.sh writes the block followed by one blank separator line; eat
    # that single trailing blank after the END marker so repeated
    # install/uninstall cycles don't accumulate blank lines.
    awk -v begin="$BEGIN_MARKER" -v end="$END_MARKER" '
        BEGIN { skipping = 0; just_ended = 0 }
        {
            if ($0 == begin) { skipping = 1; next }
            if (skipping && $0 == end) { skipping = 0; just_ended = 1; next }
            if (just_ended) { just_ended = 0; if ($0 == "") next }
            if (!skipping) print
        }
    ' "$ZSHRC.vscode-launcher.bak" > "$ZSHRC"
    echo "  Removed zsh hook block from $ZSHRC (backup: $ZSHRC.vscode-launcher.bak)"
fi

# --- Optionally remove config (shared) ---
if [ -d "$CONFIG_DIR" ]; then
    read -rp "Remove configuration at $CONFIG_DIR? (y/N): " response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        rm -rf "$CONFIG_DIR"
        echo "  Removed config: $CONFIG_DIR"
    else
        echo "  Config preserved at: $CONFIG_DIR"
    fi
fi

echo "Uninstallation complete."
