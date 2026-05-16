#!/usr/bin/env bash
# Uninstall display-mirror-toggle utility

set -euo pipefail

SCRIPT_NAME="display-mirror-toggle"
TARGET_DIR="$HOME/bin"
SYMLINK="${TARGET_DIR}/${SCRIPT_NAME}"

echo "Uninstalling ${SCRIPT_NAME}..."

if [[ -L "$SYMLINK" || -f "$SYMLINK" ]]; then
    rm -f "$SYMLINK"
    echo "Removed: ${SYMLINK}"
else
    echo "Not installed: ${SYMLINK} not found"
fi

echo "Done."
