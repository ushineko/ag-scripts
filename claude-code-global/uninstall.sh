#!/bin/bash
set -e

TARGET_DIR="$HOME/.claude"
TARGET_FILE="$TARGET_DIR/CLAUDE.md"
COMMANDS_DIR="$TARGET_DIR/commands"
POLICIES_DIR="$TARGET_DIR/policies"

echo "Uninstalling Claude Code global config..."

# Track if anything was removed
REMOVED_SOMETHING=false

# Remove CLAUDE.md if present
if [ -f "$TARGET_FILE" ]; then
    echo "Removing $TARGET_FILE..."
    rm "$TARGET_FILE"
    REMOVED_SOMETHING=true
fi

# Remove Ralph commands
if [ -f "$COMMANDS_DIR/ralph.md" ]; then
    echo "Removing /ralph command..."
    rm "$COMMANDS_DIR/ralph.md"
    REMOVED_SOMETHING=true
fi

if [ -f "$COMMANDS_DIR/ralph-setup.md" ]; then
    echo "Removing /ralph-setup command..."
    rm "$COMMANDS_DIR/ralph-setup.md"
    REMOVED_SOMETHING=true
fi

# Remove policy modules
if [ -d "$POLICIES_DIR" ]; then
    echo "Removing policy modules..."
    rm -rf "$POLICIES_DIR"
    REMOVED_SOMETHING=true
fi

if [ "$REMOVED_SOMETHING" = false ]; then
    echo "No Ralph Wiggum components found to remove."
    exit 0
fi

# Check for backup files
LATEST_BACKUP=$(ls -t "$TARGET_DIR"/CLAUDE.md.backup.* 2>/dev/null | head -1)

# Restore backup if available
if [ -n "$LATEST_BACKUP" ] && [ -f "$LATEST_BACKUP" ]; then
    echo ""
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
