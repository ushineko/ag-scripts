# Spec 005: /ralph Slash Command

**Status: COMPLETE**

## Description
Create a Claude Code slash command that triggers Ralph Loop Mode within an interactive session.

## Requirements
- Create `/ralph` command as markdown file in commands/
- Instruct Claude to enter Loop Mode
- Reference the phased workflow from global CLAUDE.md
- Support optional arguments via $ARGUMENTS
- Include completion signal instructions

## Acceptance Criteria
- [x] Command file created at `commands/ralph.md`
- [x] Documents the 6-phase workflow (Orient, Select, Implement, Validate, Record, Commit)
- [x] Includes completion signal checklist
- [x] Sets autonomous behavior rules
- [x] Supports $ARGUMENTS for additional context
- [x] Install script copies command to `~/.claude/commands/`
- [x] Uninstall script removes the command

## Implementation Notes
Created `commands/ralph.md` and updated install/uninstall scripts to handle commands directory.
