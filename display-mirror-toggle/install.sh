#!/usr/bin/env bash
# Install display-mirror-toggle utility

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="display-mirror-toggle"
TARGET_DIR="$HOME/bin"

echo "Installing ${SCRIPT_NAME}..."

chmod +x "${SCRIPT_DIR}/${SCRIPT_NAME}.sh"

mkdir -p "$TARGET_DIR"

ln -sf "${SCRIPT_DIR}/${SCRIPT_NAME}.sh" "${TARGET_DIR}/${SCRIPT_NAME}"

echo "Installed: ${TARGET_DIR}/${SCRIPT_NAME}"

if [[ ":$PATH:" != *":$TARGET_DIR:"* ]]; then
    echo ""
    echo "NOTE: ${TARGET_DIR} is not in your PATH."
    echo "Add this to your shell profile:"
    echo "  export PATH=\"\$HOME/bin:\$PATH\""
fi

echo "Done."
