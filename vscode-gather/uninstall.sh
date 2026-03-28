#!/usr/bin/env bash
set -euo pipefail

BIN_DIR="$HOME/bin"

echo "Uninstalling vscode-gather..."

rm -f "$BIN_DIR/vscode-gather"
echo "Removed: $BIN_DIR/vscode-gather"

echo "Done."
