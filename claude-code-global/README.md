# Claude Code Global Config (Ralph Wiggum Methodology)

**Version 1.1.0**

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

- **Phased Workflow**: Orient → Select → Implement → Validate → Record → Commit
- **Context Detection**: Automatically detects when running in loop mode vs interactive
- **Quality Gates**: Enforces tests passing before marking work complete
- **Git Preferences**: Conventional commits, no Co-Authored-By lines
- **Project Overrides**: Per-project `CLAUDE.md` files can extend or override defaults
- **/ralph Command**: Slash command to trigger Loop Mode within an interactive session
- **ralph-loop.sh**: External orchestrator for fully autonomous spec processing

## Installation

```bash
./install.sh
```

This installs:
- `CLAUDE.md` → `~/.claude/CLAUDE.md` (global config)
- `/ralph` command → `~/.claude/commands/ralph.md`

If you already have a global config, it will be backed up first.

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
