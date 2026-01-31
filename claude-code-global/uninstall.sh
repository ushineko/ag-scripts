#!/bin/bash
set -e

TARGET_DIR="$HOME/.claude"
TARGET_FILE="$TARGET_DIR/CLAUDE.md"

echo "Uninstalling Claude Code global config..."

if [ ! -f "$TARGET_FILE" ]; then
    echo "No global config found at $TARGET_FILE"
    exit 0
fi

# Check for backup files
LATEST_BACKUP=$(ls -t "$TARGET_DIR"/CLAUDE.md.backup.* 2>/dev/null | head -1)

# Remove the config
echo "Removing $TARGET_FILE..."
rm "$TARGET_FILE"

# Restore backup if available
if [ -n "$LATEST_BACKUP" ] && [ -f "$LATEST_BACKUP" ]; then
    echo "Found backup: $LATEST_BACKUP"
    read -p "Restore backup? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cp "$LATEST_BACKUP" "$TARGET_FILE"
        echo "Backup restored."
    fi
fi

echo ""
echo "Uninstallation complete."
