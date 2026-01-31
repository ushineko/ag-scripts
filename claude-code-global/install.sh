#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="$HOME/.claude"
TARGET_FILE="$TARGET_DIR/CLAUDE.md"
SOURCE_FILE="$SCRIPT_DIR/CLAUDE.md"
COMMANDS_DIR="$TARGET_DIR/commands"
SOURCE_COMMANDS="$SCRIPT_DIR/commands"

echo "Installing Claude Code global config (Ralph Wiggum methodology)..."

# Create target directory if it doesn't exist
if [ ! -d "$TARGET_DIR" ]; then
    echo "Creating $TARGET_DIR..."
    mkdir -p "$TARGET_DIR"
fi

# Create commands directory if it doesn't exist
if [ ! -d "$COMMANDS_DIR" ]; then
    echo "Creating $COMMANDS_DIR..."
    mkdir -p "$COMMANDS_DIR"
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

# Copy commands
if [ -d "$SOURCE_COMMANDS" ]; then
    echo "Installing slash commands..."
    for cmd in "$SOURCE_COMMANDS"/*.md; do
        if [ -f "$cmd" ]; then
            cmd_name=$(basename "$cmd")
            echo "  - /$cmd_name"
            cp "$cmd" "$COMMANDS_DIR/$cmd_name"
        fi
    done
fi

echo ""
echo "Installation complete!"
echo "The Ralph Wiggum methodology is now active for all Claude Code sessions."
echo ""
echo "Available commands:"
echo "  /ralph - Trigger Ralph Loop Mode to work through specs autonomously"
echo ""
echo "To customize for a specific project, create .claude/CLAUDE.md in that project."
