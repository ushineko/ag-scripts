#!/bin/bash
# Install bluetooth-reset utility

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="bluetooth-reset"
TARGET_DIR="$HOME/bin"

echo "Installing ${SCRIPT_NAME}..."

# Create ~/bin if it doesn't exist
mkdir -p "$TARGET_DIR"

# Create symlink
ln -sf "${SCRIPT_DIR}/${SCRIPT_NAME}.sh" "${TARGET_DIR}/${SCRIPT_NAME}"

echo "Installed: ${TARGET_DIR}/${SCRIPT_NAME}"

# Check if ~/bin is in PATH
if [[ ":$PATH:" != *":$TARGET_DIR:"* ]]; then
    echo ""
    echo "NOTE: ${TARGET_DIR} is not in your PATH."
    echo "Add this to your shell profile:"
    echo "  export PATH=\"\$HOME/bin:\$PATH\""
fi

echo "Done."
