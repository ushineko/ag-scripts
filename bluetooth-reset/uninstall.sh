#!/bin/bash
# Uninstall bluetooth-reset utility

set -euo pipefail

SCRIPT_NAME="bluetooth-reset"
TARGET_DIR="$HOME/bin"
SYMLINK="${TARGET_DIR}/${SCRIPT_NAME}"

echo "Uninstalling ${SCRIPT_NAME}..."

# Remove symlink
if [[ -L "$SYMLINK" ]]; then
    rm -f "$SYMLINK"
    echo "Removed: ${SYMLINK}"
elif [[ -f "$SYMLINK" ]]; then
    rm -f "$SYMLINK"
    echo "Removed: ${SYMLINK}"
else
    echo "Not installed: ${SYMLINK} not found"
fi

echo "Done."
