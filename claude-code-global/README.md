# Claude Code Global Config (Ralph Wiggum Methodology)

**Version 1.3.1**

A global `CLAUDE.md` configuration file for Claude Code that implements the Ralph Wiggum autonomous coding methodology—a spec-driven, iterative development workflow with quality gates and fresh context per iteration.

## Table of Contents
- [What is Ralph Wiggum?](#what-is-ralph-wiggum)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
  - [Interactive Mode](#interactive-mode-default)
  - [/ralph Command](#ralph-command)
  - [ralph-loop.sh](#ralph-loopsh)
- [Specs Structure](#specs-structure)
- [Customization](#customization)
- [Uninstallation](#uninstallation)
- [Changelog](#changelog)

## What is Ralph Wiggum?

Ralph Wiggum is an agentic development workflow based on three principles:

1. **Fresh Context Each Iteration** - Spawn a new agent process per task to prevent context degradation
2. **Spec-Driven Development** - Clear specifications with testable acceptance criteria
3. **Backpressure Via Tests** - Tests, builds, and lints act as quality gates that must pass before proceeding

The methodology supports two modes:
- **Interactive Mode**: Normal conversation, guidance, and collaboration
- **Loop Mode**: Autonomous implementation of specs with completion signals

## Features

- **Phased Workflow**: Orient → Select → Implement → Validate → Code Quality → Security → Record → Commit
- **Context Detection**: Automatically detects when running in loop mode vs interactive
- **Quality Gates**: Enforces tests passing, code quality checks, and security review before marking work complete
- **Code Quality Pass**: Checks for dead code, duplication, and poor encapsulation
- **Security Review Pass**: CVE scanning, OWASP top 10 checks, and security anti-pattern detection
- **Validation Artifacts**: Saves structured validation reports to track quality trends over time
- **Git Preferences**: Conventional commits, no Co-Authored-By lines, VPN connectivity checks
- **Project Overrides**: Per-project `CLAUDE.md` files can extend or override defaults
- **/ralph Command**: Slash command to trigger Loop Mode within an interactive session
- **ralph-loop.sh**: External orchestrator for fully autonomous spec processing
- **File Sync Workflow**: Clear procedures for keeping global config in version control

## Installation

```bash
./install.sh
```

This installs:
- `CLAUDE.md` → `~/.claude/CLAUDE.md` (global config)
- `/ralph` command → `~/.claude/commands/ralph.md`

If you already have a global config, it will be backed up first.

## Keeping Files in Sync

**IMPORTANT**: This project's `CLAUDE.md` is the canonical source that gets installed to `~/.claude/CLAUDE.md`. These two files must stay in sync.

### When updating the global methodology:

1. **Edit the version-controlled copy**: Make changes to `claude-code-global/CLAUDE.md` in this repo
2. **Sync to installed location**: Run `./install.sh` to copy changes to `~/.claude/CLAUDE.md`
3. **Commit to version control**: Commit the changes to this project
4. **Version bump**: Update the version number in README.md if changes are significant

### When changes are made directly to ~/.claude/CLAUDE.md:

If you've made changes directly to the installed file (e.g., during development):

1. Copy changes back to this project: `cp ~/.claude/CLAUDE.md claude-code-global/CLAUDE.md`
2. Review the diff carefully
3. Commit to this project's version control

This ensures the global methodology is properly tracked and can be shared/reinstalled.

## Usage

Once installed, the global config applies to all Claude Code sessions.

### Interactive Mode (Default)
Just chat normally. Claude will provide guidance, explain decisions, and help plan.

### /ralph Command

Trigger Loop Mode within an interactive Claude Code session:

```
/ralph
```

Or with additional context:

```
/ralph implement the authentication feature
```

Claude will:
1. Scan `specs/` for incomplete specs
2. Work through them in order
3. Output `<promise>DONE</promise>` when complete

### ralph-loop.sh

For fully autonomous operation with fresh context per iteration:

```bash
# Run in current directory
./ralph-loop.sh

# Run in specific project
./ralph-loop.sh /path/to/project

# Limit iterations
./ralph-loop.sh --max-iterations 10

# Dry run (show what would be done)
./ralph-loop.sh --dry-run
```

The script:
1. Finds incomplete specs in `specs/`
2. Spawns a fresh Claude Code process for each spec
3. Monitors for completion signals
4. Continues until all specs are complete or max iterations reached

## Specs Structure

Create specs in your project's `specs/` folder:

```
project/
├── specs/
│   ├── 001-user-auth.md
│   ├── 002-api-endpoints.md
│   └── 003-frontend-ui.md
└── ...
```

Each spec should include:

```markdown
# Spec 001: Feature Name

**Status: PENDING**  <!-- or COMPLETE when done -->

## Description
What needs to be built.

## Requirements
- Requirement 1
- Requirement 2

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
```

Ralph processes specs in numerical order and marks them complete when all criteria pass.

## Customization

Create a project-level `.claude/CLAUDE.md` to override or extend the global config:

```markdown
# Project-Specific Guidelines

This project follows the Ralph Wiggum methodology with these extensions:

## Environment
- Use Python 3.12+
- Tests in `tests/` folder

## Custom Quality Gates
- [ ] Type checking passes (mypy)
- [ ] Coverage > 80%
```

## Uninstallation

```bash
./uninstall.sh
```

This removes:
- `~/.claude/CLAUDE.md`
- `~/.claude/commands/ralph.md`

If a backup exists, you'll be prompted to restore it.

## Changelog

### v1.3.1
- **Bugfix: ralph-loop.sh empty specs loop** - Fixed `find_incomplete_specs` outputting a phantom newline when no incomplete specs exist, causing infinite loop until max iterations
- **Bugfix: ralph-loop.sh set -e crash** - Fixed `((iteration++))` post-increment from 0 being falsy, which killed the script on first iteration with `set -e`
- **Cleanup** - Removed unused `PROMPT_FILE` temp file and dead `get_spec_number()` function

### v1.3.0
- **Validation Artifacts** - Added workflow rule to save validation results as project artifacts in `validation-reports/`
- **Phase 6 Enhancement** - Renamed to "Record History & Validation Artifacts" with detailed artifact template
- **Quality Tracking** - Enables tracking of quality trends over time with structured validation reports
- **Example Report** - Included comprehensive validation report for v1.2.0 release as reference

### v1.2.0
- **Phase 4: Code Quality Refactor Pass** - Added conditional refactoring step to check for dead code, duplication, and poor encapsulation
- **Phase 5: Security Review Pass** - Added comprehensive security analysis including CVE scanning, OWASP top 10 checks, and security anti-patterns
- **Workflow renumbering** - Phases renumbered to accommodate new quality gates (Record History → Phase 6, Commit → Phase 7, Completion Signal → Phase 8)
- **Remote Connectivity Check** - Added git connectivity check with VPN bounce reminder
- **File Sync Documentation** - Added workflow rules and procedures for keeping `~/.claude/CLAUDE.md` and `claude-code-global/CLAUDE.md` in sync

### v1.1.0
- Added `/ralph` slash command for triggering Loop Mode
- Added `ralph-loop.sh` external orchestration script
- Added `specs/` folder with retroactive specs for this project
- Updated install/uninstall scripts to handle commands directory

### v1.0.0
- Initial release
- Ralph Wiggum methodology implementation
- Phased workflow (Orient → Select → Implement → Validate → Record → Commit)
- Context detection (Interactive vs Loop mode)
- Git preferences (conventional commits, no Co-Authored-By)
- Project override support
