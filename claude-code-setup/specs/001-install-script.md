# Spec 001: Install Script

**Status: COMPLETE**

## Description
Create installation script for Claude Code CLI tool.

## Requirements
- Check for Node.js and npm dependencies
- Install @anthropic-ai/claude-code globally via npm
- Verify installation

## Acceptance Criteria
- [x] Checks for Node.js/npm presence
- [x] Errors gracefully if dependencies missing
- [x] Installs package globally
- [x] Verifies installation succeeded

## Implementation Notes
Created `install.sh` with dependency checking and npm global install.
