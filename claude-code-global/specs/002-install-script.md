# Spec 002: Install Script

**Status: COMPLETE**

## Description
Create an installation script that copies the global CLAUDE.md to the user's `~/.claude/` directory.

## Requirements
- Create `~/.claude/` directory if it doesn't exist
- Backup existing config before overwriting
- Copy CLAUDE.md to target location
- Provide clear feedback to user

## Acceptance Criteria
- [x] Creates target directory if missing
- [x] Backs up existing config with timestamp
- [x] Copies config file successfully
- [x] Outputs installation status messages
- [x] Uses `set -e` for error handling

## Implementation Notes
Created `install.sh` with backup functionality using timestamped filenames.
