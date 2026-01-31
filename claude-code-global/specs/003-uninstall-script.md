# Spec 003: Uninstall Script

**Status: COMPLETE**

## Description
Create an uninstallation script that removes the global CLAUDE.md and optionally restores a backup.

## Requirements
- Remove the installed CLAUDE.md from `~/.claude/`
- Detect existing backups
- Offer to restore the most recent backup
- Handle case where no config exists

## Acceptance Criteria
- [x] Removes `~/.claude/CLAUDE.md` if it exists
- [x] Finds most recent backup file
- [x] Prompts user to restore backup
- [x] Handles missing config gracefully
- [x] Uses `set -e` for error handling

## Implementation Notes
Created `uninstall.sh` with backup detection and optional restore functionality.
