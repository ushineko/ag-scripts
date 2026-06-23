#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing vscode-gather..."

if [[ "$OSTYPE" == "darwin"* ]]; then
    BIN_DIR="/usr/local/bin"
    mkdir -p "$BIN_DIR"
    ln -sf "$SCRIPT_DIR/gather.sh" "$BIN_DIR/vscode-gather"
    echo "Symlinked: $BIN_DIR/vscode-gather -> $SCRIPT_DIR/gather.sh"

    echo ""
    echo "macOS note: Window gathering requires Accessibility access."
    echo "  Grant access in: System Settings → Privacy & Security → Accessibility"
    echo "  Add your terminal app (e.g., Terminal.app, iTerm2)."
    if ! osascript -e 'tell application "System Events" to get name of first process whose frontmost is true' >/dev/null 2>&1; then
        echo ""
        echo "  ⚠ Accessibility access is NOT currently granted."
        echo "  Opening System Settings..."
        open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility" 2>/dev/null || true
    else
        echo "  ✓ Accessibility access is already granted."
    fi
else
    BIN_DIR="$HOME/bin"
    mkdir -p "$BIN_DIR"
    ln -sf "$SCRIPT_DIR/gather.sh" "$BIN_DIR/vscode-gather"
    echo "Symlinked: $BIN_DIR/vscode-gather -> $SCRIPT_DIR/gather.sh"
    echo "Make sure ~/bin is in your PATH."
fi

echo "Done."
