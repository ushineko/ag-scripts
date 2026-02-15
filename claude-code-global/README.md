# Claude Code Global Config (Ralph Wiggum Methodology)

**Version 2.0.0**

A global `CLAUDE.md` configuration for Claude Code that implements the Ralph Wiggum autonomous coding methodology — a spec-driven, iterative development workflow with quality gates, security review, and composable policy modules.

## Table of Contents
- [Architecture](#architecture)
- [What is Ralph Wiggum?](#what-is-ralph-wiggum)
- [Features](#features)
- [Installation](#installation)
- [Upgrading from v1.x](#upgrading-from-v1x)
- [Usage](#usage)
  - [Interactive Mode](#interactive-mode-default)
  - [/ralph Command](#ralph-command)
  - [/ralph-setup Command](#ralph-setup-command)
  - [ralph-loop.sh](#ralph-loopsh)
  - [ralph-prompt.sh](#ralph-promptsh)
- [Specs Structure](#specs-structure)
- [Customization](#customization)
- [Uninstallation](#uninstallation)
- [Keeping Files in Sync](#keeping-files-in-sync)
- [Changelog](#changelog)

## Architecture

As of v2.0, claude-code-global uses a **core + policies** architecture:

```
~/.claude/
├── CLAUDE.md              # Core methodology (~530 lines) — universal rules
├── policies/              # Composable policy modules
│   ├── languages/         # python.md, go.md, bash.md
│   ├── git/               # standard.md, platform-backend.md, simple.md
│   ├── release-safety/    # full.md, simplified.md, minimal.md
│   └── integrations/      # jira-mcp.md, gitlab-glab.md
└── commands/              # /ralph, /ralph-setup skills
```

**Core** (`CLAUDE.md`) contains universal methodology: phases, philosophy, modes, security review, test philosophy, quality gates, communication standards.

**Policies** contain project-specific concerns: language coding standards, git workflows, release safety details, external tool integrations. Each project selects which policies to activate via `/ralph-setup`.

**Per-project config** (`.claude/CLAUDE.md` in each repo) references selected policies and any relaxed rules:

```markdown
## Selected Policies
Load the following policy modules from `~/.claude/policies/`:
- `languages/python.md`
- `git/standard.md`
- `release-safety/full.md`
- `integrations/jira-mcp.md`
```

| Layer | Scope | Updated by |
|-------|-------|------------|
| Core `CLAUDE.md` | All projects | `./install.sh` from claude-code-global |
| Policy modules | All projects (available) | `./install.sh` from claude-code-global |
| Project `.claude/CLAUDE.md` | One project | `/ralph-setup` (one-time per project) |

## What is Ralph Wiggum?

Ralph Wiggum is an agentic development workflow based on three principles:

1. **Fresh Context Each Iteration** - Spawn a new agent process per task to prevent context degradation
2. **Spec-Driven Development** - Clear specifications with testable acceptance criteria
3. **Backpressure Via Tests** - Tests, builds, and lints act as quality gates that must pass before proceeding

The methodology supports two modes:
- **Interactive Mode** (recommended default): Collaboration with human-in-the-loop for design decisions
- **Loop Mode**: Bounded autonomous implementation of specs with completion signals

## Features

- **Phased Workflow**: Orient → Select → Implement → Validate → Code Quality → Security → Release Safety → Record → Commit
- **Context Detection**: Automatically detects when running in loop mode vs interactive
- **Quality Gates**: Enforces tests passing, code quality checks, and security review before marking work complete
- **Test Philosophy**: Tests as behavioral contracts, not coverage targets. Anti-pattern detection for over-mocking
- **AI Tool Input Hygiene**: Context exclusion, credential display safety, prompt-before-expose
- **Security Review Pass**: CVE scanning, OWASP top 10 checks, and security anti-pattern detection
- **Policy Module System**: 11 composable policy modules for language, git, release safety, and integration standards
- **Validation Artifacts**: Saves structured validation reports to track quality trends over time
- **Project Overrides**: Per-project `CLAUDE.md` files can extend or override defaults
- **/ralph Command**: Slash command to trigger Loop Mode within an interactive session
- **/ralph-setup Command**: Guided setup wizard for per-project policy selection
- **ralph-loop.sh**: External orchestrator for fully autonomous spec processing
- **ralph-prompt.sh**: General-purpose prompt iteration loop for tasks without specs

## Installation

```bash
cd claude-code-global
./install.sh
```

This installs:

| Source | Destination | Purpose |
|--------|-------------|---------|
| `CLAUDE.md` | `~/.claude/CLAUDE.md` | Core methodology |
| `policies/` | `~/.claude/policies/` | 11 composable policy modules |
| `commands/ralph.md` | `~/.claude/commands/ralph.md` | `/ralph` slash command |
| `commands/ralph-setup.md` | `~/.claude/commands/ralph-setup.md` | `/ralph-setup` wizard |

If you already have a global config, it will be backed up first. Old policies are replaced entirely to catch renames and deletions.

## Upgrading from v1.x

If you're already using Ralph with the v1.x monolithic CLAUDE.md:

### What Changed

In v1.x, `~/.claude/CLAUDE.md` was a single ~500-line file containing everything. In v2.0, it's split into a ~530-line core + 11 composable policy modules in `~/.claude/policies/`.

The core methodology (phases, security, test philosophy, quality gates) still applies to every project. Language-specific coding standards, git workflow guidance, release safety details, and integration patterns are now in policies — they only activate when a project's `.claude/CLAUDE.md` lists them in `## Selected Policies`.

### Upgrade Steps

1. Run the installer:
   ```bash
   cd claude-code-global && ./install.sh
   ```

2. Run `/ralph-setup` in each active project to select policies.

3. Commit the updated `.claude/CLAUDE.md` in each project.

### What If You Skip Step 2?

Projects without `## Selected Policies` continue to work — core methodology applies in full. What's absent is language-specific coding standards, git workflow guidance beyond basic conventions, stack-specific release safety checklists, and external tool integration guidance.

## Usage

Once installed, the global config applies to all Claude Code sessions.

### Interactive Mode (Default)

Just chat normally. Claude will provide guidance, surface design decisions, and collaborate on implementation. This is the recommended mode for most work.

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

### /ralph-setup Command

Guided setup wizard for project-specific customization:

```
/ralph-setup
```

Walks you through:
- Selecting policies: languages (Python, Go, Bash), git workflow, release safety, integrations
- Which guidelines to keep strict vs. relax
- Environment-specific settings
- Additional security requirements

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

### ralph-prompt.sh

General-purpose prompt iteration for tasks without specs:

```bash
# Basic usage - run prompt 5 times
./ralph-prompt.sh "Continue implementing the feature" --max-iterations=5

# YOLO mode (no permission prompts) - use in sandboxed environments only
./ralph-prompt.sh "Fix all lint errors" --max-iterations=3 --yolo

# Specify working directory
./ralph-prompt.sh "Refactor the module" --max-iterations=10 --cwd ~/projects/myapp

# Without cclean formatting (raw JSON output)
./ralph-prompt.sh "Add tests" --max-iterations=2 --no-cclean
```

**Dependencies**: Requires [cclean](https://github.com/ariel-frischer/claude-clean) for formatted output. Use `--no-cclean` for raw JSON if not installed.

**When to use which script:**

| Use Case | Script |
|----------|--------|
| Working through specs in `specs/` folder | `ralph-loop.sh` |
| One-off iterative task with a prompt | `ralph-prompt.sh` |
| Need completion detection (`DONE` signal) | `ralph-loop.sh` |
| Fixed number of iterations regardless of result | `ralph-prompt.sh` |
| Permission-free autonomous work (sandboxed) | `ralph-prompt.sh --yolo` |

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

### Quick Start (Guided)
Run `/ralph-setup` for an interactive wizard that creates your project configuration.

### Manual Setup
Create project-level `.claude/CLAUDE.md` to extend or override defaults:

```markdown
# Project-Specific Guidelines

## Selected Policies
Load the following policy modules from `~/.claude/policies/`:
- `languages/python.md`
- `git/standard.md`
- `release-safety/simplified.md`

## Environment
- Python 3.12+ required
- Additional quality gates: mypy type checking

## Custom Security Requirements
- All API endpoints require authentication
```

### Customization Philosophy

**Strict by default, relaxable by user** - The global configuration is intentionally strict. Projects can loosen requirements where appropriate.

| Category | Default | Can Relax? | Can Extend? |
|----------|---------|------------|-------------|
| Validation Reports | Required every commit | Yes | Yes |
| Code Quality Checks | Always run | Yes | Yes |
| Test Requirements | Must pass | Yes | Yes |
| Communication Standards | Factual, no superlatives | Yes | Yes |
| Tool Installation | Always ask | Yes | Yes |
| Git Standards | Conventional commits | Partial | Yes |
| Release Safety | Full checklist | Yes | Yes |
| **Security Review** | **OWASP, CVE scanning** | **No** | **Yes** |
| **Secrets Detection** | **No hardcoded secrets** | **No** | **Yes** |

**Security is mandatory**: Security checks cannot be disabled, only extended with additional rules.

## Uninstallation

```bash
./uninstall.sh
```

This removes:
- `~/.claude/CLAUDE.md`
- `~/.claude/commands/ralph.md`
- `~/.claude/commands/ralph-setup.md`
- `~/.claude/policies/` directory

If a backup exists, you'll be prompted to restore it.

## Keeping Files in Sync

**IMPORTANT**: This project's `CLAUDE.md` is the canonical source that gets installed to `~/.claude/CLAUDE.md`. These two files must stay in sync.

### When updating the global methodology:

1. **Edit the version-controlled copy**: Make changes to `claude-code-global/CLAUDE.md`
2. **Sync to installed location**: Run `./install.sh`
3. **Commit to version control**: Commit the changes
4. **Version bump**: Update the version number in this README if changes are significant

### When changes are made directly to ~/.claude/CLAUDE.md:

If you've made changes directly to the installed file (e.g., during development):

1. Copy changes back to this project: `cp ~/.claude/CLAUDE.md claude-code-global/CLAUDE.md`
2. Review the diff carefully
3. Commit to version control

## Changelog

### v2.0.0
- **Policy Module System**: Core CLAUDE.md decoupled from project-specific concerns. Core contains universal methodology (phases, security, test philosophy, quality gates). Language standards, git workflows, release safety details, and integration patterns moved to composable policy modules in `policies/`
- **11 policy modules** across 4 categories:
  - **Languages**: `python.md`, `go.md`, `bash.md` — coding standards per language
  - **Git**: `standard.md` (most projects), `platform-backend.md` (multi-branch, cherry-pick, migrations), `simple.md` (docs repos)
  - **Release Safety**: `full.md` (Expand-Migrate-Contract, stack-specific), `simplified.md` (internal tools), `minimal.md` (prototypes)
  - **Integrations**: `jira-mcp.md` (mcp-atlassian), `gitlab-glab.md` (glab CLI)
- **`/ralph-setup` command**: Guided wizard for per-project policy selection. Detects v1.x configs and offers upgrade path with auto-suggestions based on project file types
- **New: AI Tool Input Hygiene**: Context exclusion, credential display safety, prompt-before-expose
- **New: Test Philosophy**: Tests as behavioral contracts, mock anti-patterns, coverage as diagnostic
- **New: ralph-prompt.sh**: General-purpose prompt iteration loop for tasks without specs
- **Human-in-the-loop by default**: Interactive Mode repositioned as recommended default; Loop Mode scoped to low-ambiguity mechanical tasks
- **Phase 2/3 test checkpoints**: Test strategy checkpoint before writing tests; test contract quality review after
- **Installer updates**: `install.sh` / `uninstall.sh` now deploy `policies/` directory and `/ralph-setup` command
- **Backward compatible**: Existing v1.x project configs continue to work (core methodology applies). Policy-specific guidance activates after re-running `/ralph-setup`

### v1.3.1
- **Bugfix: ralph-loop.sh empty specs loop** - Fixed `find_incomplete_specs` outputting a phantom newline when no incomplete specs exist, causing infinite loop until max iterations
- **Bugfix: ralph-loop.sh set -e crash** - Fixed `((iteration++))` post-increment from 0 being falsy, which killed the script on first iteration with `set -e`
- **Cleanup** - Removed unused `PROMPT_FILE` temp file and dead `get_spec_number()` function

### v1.3.0
- **Validation Artifacts** - Added workflow rule to save validation results as project artifacts in `validation-reports/`
- **Phase 6 Enhancement** - Renamed to "Record History & Validation Artifacts" with detailed artifact template
- **Quality Tracking** - Enables tracking of quality trends over time with structured validation reports

### v1.2.0
- **Phase 4: Code Quality Refactor Pass** - Added conditional refactoring step to check for dead code, duplication, and poor encapsulation
- **Phase 5: Security Review Pass** - Added comprehensive security analysis including CVE scanning, OWASP top 10 checks, and security anti-patterns
- **Remote Connectivity Check** - Added git connectivity check with VPN bounce reminder
- **File Sync Documentation** - Added workflow rules for keeping configs in sync

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
