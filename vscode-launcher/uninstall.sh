#!/bin/bash
set -euo pipefail

APP_NAME="vscode-launcher"
LOOKUP_NAME="vscl-tmux-lookup"
INSTALL_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
CONFIG_DIR="$HOME/.config/vscode-launcher"
ZSHRC="$HOME/.zshrc"

BEGIN_MARKER="# --- vscode-launcher tmux hook (BEGIN) ---"
END_MARKER="# --- vscode-launcher tmux hook (END) ---"

echo "Uninstalling VSCode Launcher..."

# --- Remove symlinks ---
if [ -L "$INSTALL_DIR/$APP_NAME" ]; then
    rm "$INSTALL_DIR/$APP_NAME"
    echo "  Removed symlink: $INSTALL_DIR/$APP_NAME"
fi

if [ -L "$INSTALL_DIR/$LOOKUP_NAME" ]; then
    rm "$INSTALL_DIR/$LOOKUP_NAME"
    echo "  Removed symlink: $INSTALL_DIR/$LOOKUP_NAME"
fi

# --- Remove desktop entry ---
if [ -f "$DESKTOP_DIR/$APP_NAME.desktop" ]; then
    rm "$DESKTOP_DIR/$APP_NAME.desktop"
    echo "  Removed desktop entry: $DESKTOP_DIR/$APP_NAME.desktop"
fi
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

# --- Remove zsh hook block (inclusive) ---
if [ -f "$ZSHRC" ] && grep -Fq "$BEGIN_MARKER" "$ZSHRC"; then
    cp "$ZSHRC" "$ZSHRC.vscode-launcher.bak"
    awk -v begin="$BEGIN_MARKER" -v end="$END_MARKER" '
        BEGIN { skipping = 0 }
        {
            if ($0 == begin) { skipping = 1; next }
            if (skipping && $0 == end) { skipping = 0; next }
            if (!skipping) print
        }
    ' "$ZSHRC.vscode-launcher.bak" > "$ZSHRC"
    echo "  Removed zsh hook block from $ZSHRC (backup: $ZSHRC.vscode-launcher.bak)"
fi

# --- Optionally remove config ---
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
