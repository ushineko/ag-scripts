#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="$HOME/bin"

echo "Installing vscode-gather..."

mkdir -p "$BIN_DIR"
ln -sf "$SCRIPT_DIR/gather.sh" "$BIN_DIR/vscode-gather"

echo "Symlinked: $BIN_DIR/vscode-gather -> $SCRIPT_DIR/gather.sh"
echo "Done. Make sure ~/bin is in your PATH."
