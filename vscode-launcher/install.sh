#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="vscode-launcher"
LOOKUP_NAME="vscl-tmux-lookup"
MAIN_SCRIPT="$SCRIPT_DIR/vscode_launcher.py"
LOOKUP_SCRIPT="$SCRIPT_DIR/tmux_lookup.py"
HOOK_FILE="$SCRIPT_DIR/tmux_hook.zsh"
ZSHRC="$HOME/.zshrc"

BEGIN_MARKER="# --- vscode-launcher tmux hook (BEGIN) ---"
END_MARKER="# --- vscode-launcher tmux hook (END) ---"

# --- Platform detection ---
# macOS gets a CLI + menu-bar install (symlink into /usr/local/bin, autostart
# via a LaunchAgent). Linux/KDE gets the full desktop integration (hicolor
# icon, .desktop menu + autostart entries, sycoca refresh). The dependency
# check and the tmux zsh hook are shared — tmux works on both platforms.
if [[ "$OSTYPE" == "darwin"* ]]; then
    IS_MACOS=1
    INSTALL_DIR="/usr/local/bin"
    LAUNCH_AGENT_DIR="$HOME/Library/LaunchAgents"
    LAUNCH_AGENT_LABEL="com.vscode-launcher.agent"
    LAUNCH_AGENT_PLIST="$LAUNCH_AGENT_DIR/$LAUNCH_AGENT_LABEL.plist"
else
    IS_MACOS=0
    INSTALL_DIR="$HOME/.local/bin"
    DESKTOP_DIR="$HOME/.local/share/applications"
    AUTOSTART_DIR="$HOME/.config/autostart"
    ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
    ICON_SOURCE="$SCRIPT_DIR/$APP_NAME.svg"
fi

echo "Installing VSCode Launcher..."

# --- Dependencies (shared) ---
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is required but not found."
    exit 1
fi

if ! python3 -c "import PyQt6" &>/dev/null; then
    echo "Error: PyQt6 is required. Install it with: pip3 install PyQt6"
    exit 1
fi

# psutil is optional — it powers the Launched column's per-window start time
# on macOS (Linux uses /proc and needs no dep). Absent, the column shows an
# em-dash for pre-existing windows rather than crashing.
if [[ "$IS_MACOS" -eq 1 ]] && ! python3 -c "import psutil" &>/dev/null; then
    echo "Note: psutil not found. The Launched column will show '—' for"
    echo "      already-open VSCode windows. Enable it with: pip3 install --user psutil"
fi

if ! command -v tmux &>/dev/null; then
    echo "Warning: tmux not found on PATH. The launcher will run but session switching will be disabled."
fi

# --- 'code' CLI verification (shared, with extra macOS hijack check) ---
# Risk #3 from spec 013: on macOS the /usr/local/bin/code symlink is commonly
# hijacked by other editors (Cursor, VSCodium) that ship a `code` shim. Verify
# it resolves to "Visual Studio Code.app" and warn if it points elsewhere.
if ! command -v code &>/dev/null; then
    echo "Warning: 'code' (VSCode CLI) not found on PATH. The launcher will run but cannot open workspaces."
elif [[ "$IS_MACOS" -eq 1 ]]; then
    CODE_TARGET="$(readlink -f "$(command -v code)" 2>/dev/null || command -v code)"
    if [[ "$CODE_TARGET" != *"Visual Studio Code.app"* ]]; then
        echo "Warning: 'code' on PATH resolves to:"
        echo "           $CODE_TARGET"
        echo "         This does not look like Visual Studio Code (possibly hijacked by"
        echo "         another editor). Repoint it with VS Code's"
        echo "         'Shell Command: Install code command in PATH' to open workspaces correctly."
    fi
fi

# --- Linux-only: qdbus6 / vscode-gather (KWin row actions + window placement) ---
if [[ "$IS_MACOS" -eq 0 ]]; then
    if ! command -v qdbus6 &>/dev/null; then
        echo "Warning: qdbus6 not found on PATH. Stop / Activate row buttons will be no-ops."
    fi
    if ! command -v vscode-gather &>/dev/null; then
        echo "Warning: 'vscode-gather' not found on PATH. Windows will not be auto-placed/maximized."
        echo "         Install the sibling 'vscode-gather' sub-project to enable this."
    fi
fi

# --- Make scripts executable + symlink (shared) ---
mkdir -p "$INSTALL_DIR"
chmod +x "$MAIN_SCRIPT" "$LOOKUP_SCRIPT"

ln -sf "$MAIN_SCRIPT" "$INSTALL_DIR/$APP_NAME"
echo "  Symlink: $INSTALL_DIR/$APP_NAME -> $MAIN_SCRIPT"

ln -sf "$LOOKUP_SCRIPT" "$INSTALL_DIR/$LOOKUP_NAME"
echo "  Symlink: $INSTALL_DIR/$LOOKUP_NAME -> $LOOKUP_SCRIPT"

if [[ "$IS_MACOS" -eq 1 ]]; then
    # --- macOS: LaunchAgent for the tray daemon ---
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
        <string>$INSTALL_DIR/$APP_NAME</string>
        <string>--tray</string>
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

    # Reload the agent so the running definition matches what we just wrote.
    # bootout is best-effort (no-op if not currently loaded); bootstrap loads it.
    GUI_TARGET="gui/$(id -u)"
    launchctl bootout "$GUI_TARGET/$LAUNCH_AGENT_LABEL" 2>/dev/null || true
    if launchctl bootstrap "$GUI_TARGET" "$LAUNCH_AGENT_PLIST" 2>/dev/null; then
        echo "  Loaded LaunchAgent (tray daemon will start now and on each login)."
    else
        echo "  (Could not auto-load the LaunchAgent. It will start on next login,"
        echo "   or start the daemon now with: $APP_NAME --tray &)"
    fi
else
    # --- Linux: hicolor icon + .desktop menu entry + autostart entry ---
    mkdir -p "$DESKTOP_DIR" "$AUTOSTART_DIR" "$ICON_DIR"

    if [ -f "$ICON_SOURCE" ]; then
        cp "$ICON_SOURCE" "$ICON_DIR/$APP_NAME.svg"
        echo "  Icon: $ICON_DIR/$APP_NAME.svg"
        gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
    fi

    cp "$SCRIPT_DIR/$APP_NAME.desktop" "$DESKTOP_DIR/$APP_NAME.desktop"
    echo "  Desktop entry: $DESKTOP_DIR/$APP_NAME.desktop"
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
    # KDE's sycoca caches desktop-entry Icon= values; without an explicit rebuild,
    # KRunner and the app menu keep showing the old icon (or a blank fallback
    # when the old Icon= name is renamed). kbuildsycoca6 is the canonical refresh.
    kbuildsycoca6 --noincremental 2>/dev/null || kbuildsycoca5 --noincremental 2>/dev/null || true

    # --- Autostart entry (tray-resident daemon) ---
    # Generated rather than copied from the menu .desktop because it needs a
    # different Exec line (--tray) and an X-GNOME-Autostart-enabled hint. KDE
    # and GNOME both honor ~/.config/autostart per the XDG Autostart spec.
    cat > "$AUTOSTART_DIR/$APP_NAME.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=VSCode Launcher (tray daemon)
Comment=Tray-resident daemon hosting the global popup hotkey
Exec=$INSTALL_DIR/$APP_NAME --tray
Icon=$APP_NAME
Terminal=false
Categories=Development;Utility;
X-GNOME-Autostart-enabled=true
StartupWMClass=$APP_NAME
EOF
    echo "  Autostart entry: $AUTOSTART_DIR/$APP_NAME.desktop"
    echo "  (Tray daemon will start on next login. To start it now without"
    echo "   logging out: $APP_NAME --tray &)"
fi

# --- Install zsh hook idempotently (shared) ---
if [ ! -f "$ZSHRC" ]; then
    echo "  Creating $ZSHRC"
    touch "$ZSHRC"
fi

if grep -Fq "$BEGIN_MARKER" "$ZSHRC"; then
    # Replace existing block IN PLACE so users always get the latest hook without
    # moving it (we assume the block is already where the user wants it).
    awk -v begin="$BEGIN_MARKER" -v end="$END_MARKER" -v hook_file="$HOOK_FILE" '
        BEGIN { skipping = 0 }
        {
            if ($0 == begin) {
                skipping = 1
                while ((getline line < hook_file) > 0) print line
                close(hook_file)
                next
            }
            if (skipping && $0 == end) { skipping = 0; next }
            if (!skipping) print
        }
    ' "$ZSHRC" > "$ZSHRC.vscode-launcher.tmp"
    mv "$ZSHRC.vscode-launcher.tmp" "$ZSHRC"
    echo "  Replaced existing zsh hook in $ZSHRC (updated to latest, position unchanged)"
else
    # Fresh install: find the first line that auto-attaches to tmux and insert BEFORE it.
    # Falls back to appending at end if no such line is detected.
    # Detection patterns (case-insensitive):
    #   tmux new-session / tmux attach / tmux a / initialize_tmux / bare `tmux` call
    insert_line=$(awk '
        /^[[:space:]]*(initialize_tmux|tmux[[:space:]]+(new-session|attach|a)([[:space:]]|$))/ {
            print NR; exit
        }
    ' "$ZSHRC")

    if [[ -n "$insert_line" ]]; then
        head -n $((insert_line - 1)) "$ZSHRC" > "$ZSHRC.vscode-launcher.tmp"
        cat "$HOOK_FILE" >> "$ZSHRC.vscode-launcher.tmp"
        echo "" >> "$ZSHRC.vscode-launcher.tmp"
        tail -n +$insert_line "$ZSHRC" >> "$ZSHRC.vscode-launcher.tmp"
        mv "$ZSHRC.vscode-launcher.tmp" "$ZSHRC"
        echo "  Installed zsh hook into $ZSHRC (before tmux auto-attach on line $insert_line)"
    else
        echo "" >> "$ZSHRC"
        cat "$HOOK_FILE" >> "$ZSHRC"
        echo "  Installed zsh hook at end of $ZSHRC"
        echo "  NOTE: if your zshrc auto-attaches to tmux (e.g. \"tmux new-session\" or"
        echo "        \"initialize_tmux\"), move the hook block to run BEFORE that line."
    fi
fi
echo "  (Open a new zsh session for the hook to take effect.)"

echo "Installation complete!"
echo "Run with: $APP_NAME"
