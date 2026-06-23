#!/usr/bin/env bash
set -euo pipefail

echo "Uninstalling vscode-gather..."

if [[ "$OSTYPE" == "darwin"* ]]; then
    BIN_DIR="/usr/local/bin"
else
    BIN_DIR="$HOME/bin"
fi

rm -f "$BIN_DIR/vscode-gather"
echo "Removed: $BIN_DIR/vscode-gather"

echo "Done."
