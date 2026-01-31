#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="$HOME/.claude"
TARGET_FILE="$TARGET_DIR/CLAUDE.md"
SOURCE_FILE="$SCRIPT_DIR/CLAUDE.md"

echo "Installing Claude Code global config (Ralph Wiggum methodology)..."

# Create target directory if it doesn't exist
if [ ! -d "$TARGET_DIR" ]; then
    echo "Creating $TARGET_DIR..."
    mkdir -p "$TARGET_DIR"
fi

# Backup existing config if present
if [ -f "$TARGET_FILE" ]; then
    BACKUP_FILE="$TARGET_FILE.backup.$(date +%Y%m%d_%H%M%S)"
    echo "Backing up existing config to $BACKUP_FILE..."
    cp "$TARGET_FILE" "$BACKUP_FILE"
fi

# Copy the config
echo "Copying CLAUDE.md to $TARGET_FILE..."
cp "$SOURCE_FILE" "$TARGET_FILE"

echo ""
echo "Installation complete!"
echo "The Ralph Wiggum methodology is now active for all Claude Code sessions."
echo ""
echo "To customize for a specific project, create .claude/CLAUDE.md in that project."
