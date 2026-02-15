#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="$HOME/.claude"
TARGET_FILE="$TARGET_DIR/CLAUDE.md"
SOURCE_FILE="$SCRIPT_DIR/CLAUDE.md"
COMMANDS_DIR="$TARGET_DIR/commands"
SOURCE_COMMANDS="$SCRIPT_DIR/commands"
POLICIES_DIR="$TARGET_DIR/policies"
SOURCE_POLICIES="$SCRIPT_DIR/policies"

echo "Installing Claude Code global config (Ralph Wiggum methodology v2.0)..."

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

# Copy the core config
echo "Copying core CLAUDE.md to $TARGET_FILE..."
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

# Install policy modules
if [ -d "$SOURCE_POLICIES" ]; then
    echo "Installing policy modules..."
    # Remove old policies to catch renames/deletions
    rm -rf "$POLICIES_DIR"
    cp -r "$SOURCE_POLICIES" "$POLICIES_DIR"
    # List installed policies
    find "$POLICIES_DIR" -name "*.md" -printf "  - %P\n" | sort
fi

echo ""
echo "Installation complete!"
echo "The Ralph Wiggum methodology is now active for all Claude Code sessions."
echo ""
echo "Available commands:"
echo "  /ralph       - Trigger Ralph Loop Mode to work through specs autonomously"
echo "  /ralph-setup - Guided setup wizard for project customization"
echo ""
echo "Installed policy modules are at: $POLICIES_DIR"
echo ""
echo "NOTE: If upgrading from v1.x, run /ralph-setup in each project to select"
echo "language, git, and release-safety policies. Projects work without this step"
echo "but won't have language-specific or git workflow guidance until configured."
