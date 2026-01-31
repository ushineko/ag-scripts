# Spec 002: Uninstall Script

**Status: COMPLETE**

## Description
Create uninstallation script for Claude Code CLI.

## Requirements
- Remove globally installed npm package
- Clean removal without affecting other packages

## Acceptance Criteria
- [x] Uninstalls @anthropic-ai/claude-code globally
- [x] Provides feedback on completion

## Implementation Notes
Created `uninstall.sh` for npm global uninstall.
