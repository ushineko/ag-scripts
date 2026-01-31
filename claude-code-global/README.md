# Claude Code Global Config (Ralph Wiggum Methodology)

**Version 1.0.0**

A global `CLAUDE.md` configuration file for Claude Code that implements the Ralph Wiggum autonomous coding methodology—a spec-driven, iterative development workflow with quality gates and fresh context per iteration.

## Table of Contents
- [What is Ralph Wiggum?](#what-is-ralph-wiggum)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
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

## Installation

```bash
./install.sh
```

This copies `CLAUDE.md` to `~/.claude/CLAUDE.md`. If you already have a global config, it will be backed up first.

## Usage

Once installed, the global config applies to all Claude Code sessions. The workflow phases are:

### Interactive Mode (Default)
Just chat normally. Claude will provide guidance, explain decisions, and help plan.

### Loop Mode
Triggered when working through specs systematically. Claude will:
1. Read specs from `specs/` folder
2. Implement one task per iteration
3. Run tests and quality gates
4. Output `<promise>DONE</promise>` on completion

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

This removes `~/.claude/CLAUDE.md`. If a backup exists, it will be restored.

## Changelog

### v1.0.0
- Initial release
- Ralph Wiggum methodology implementation
- Phased workflow (Orient → Select → Implement → Validate → Record → Commit)
- Context detection (Interactive vs Loop mode)
- Git preferences (conventional commits, no Co-Authored-By)
- Project override support
