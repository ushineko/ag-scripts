---
description: Guided setup for project-specific CLAUDE.md customization
argument-hint: [project-path]
---

# Project Configuration Setup (v2.0)

You are now entering **Setup Mode**. Guide the user through creating a customized project-specific `.claude/CLAUDE.md` file with policy module selections.

## Philosophy

- **Strict by default**: Global guidelines are intentionally strict
- **Relaxable by user**: Users can loosen requirements where appropriate for their project
- **Security is mandatory**: Security checks cannot be disabled, only extended
- **Policies are composable**: Language, git, release safety, and integration policies are selected per-project

## Setup Process

### Step 0: Detect Existing Configuration

First, check if a project-specific `.claude/CLAUDE.md` already exists:
- If YES and it has a `## Selected Policies` section: Ask if user wants to modify existing config
- If YES but NO `## Selected Policies` section: **v1.x upgrade detected** — offer to upgrade (preserve existing settings, add policy selection)
- If NO: Create the directory structure and start fresh

**For v1.x upgrades**: Read the existing config to preserve relaxed rules, additional rules, environment settings, and security extensions. Then proceed to policy selection.

### Step 1: Policy Selection — Languages

Use the AskUserQuestion tool. Auto-suggest based on project file types when possible:
- Presence of `.py` files → suggest `languages/python.md`
- Presence of `.go` files → suggest `languages/go.md`
- Presence of `.sh` files → suggest `languages/bash.md`

**Question**: "Which language policies should be active for this project?"

Options (multi-select):
- [ ] Python (`languages/python.md`) — Python coding standards, style, tooling
- [ ] Go (`languages/go.md`) — Go coding standards, project structure, concurrency
- [ ] Bash (`languages/bash.md`) — Shell script standards, safety, shellcheck
- [ ] None — No language-specific policies

### Step 2: Policy Selection — Git Workflow

Auto-suggest based on project context:
- Presence of Django migrations or multi-branch references → suggest `git/platform-backend.md`
- Documentation/config projects → suggest `git/simple.md`
- Otherwise → suggest `git/standard.md`

**Question**: "Which git workflow policy fits this project?"

Options (single-select):
- [ ] Standard (`git/standard.md`) — Conventional commits, connectivity checks, force-push safety (Recommended)
- [ ] Platform-backend (`git/platform-backend.md`) — Multi-branch, cherry-pick workflows, Django migrations
- [ ] Simple (`git/simple.md`) — Conventional commits only, minimal rules
- [ ] None — No git-specific policy (use only core methodology)

### Step 3: Policy Selection — Release Safety

**Question**: "What level of release safety review does this project need?"

Options (single-select):
- [ ] Full (`release-safety/full.md`) — Expand-Migrate-Contract, feature flags, stack-specific checklists (Recommended for production services)
- [ ] Simplified (`release-safety/simplified.md`) — Document rollback approach, skip formal checklists (For internal tools)
- [ ] Minimal (`release-safety/minimal.md`) — Acknowledge risk, git revert sufficient (For prototypes)
- [ ] None — Use only the generic Phase 5.5 checklist from core

### Step 4: Policy Selection — Integrations

**Question**: "Which external tool integrations do you use?"

Options (multi-select):
- [ ] Jira via MCP (`integrations/jira-mcp.md`) — mcp-atlassian setup and Jira workflow
- [ ] GitLab via glab (`integrations/gitlab-glab.md`) — glab CLI operations and notes
- [ ] None — No integration policies

### Step 5: Relaxable Rules

Walk through each relaxable category. Present options clearly.

#### Category 1: Validation Reports (Relaxable)
**Default**: REQUIRED before every code commit

Options:
- [ ] Keep strict (required for all commits) - Recommended
- [ ] Relax to milestones only (major features, releases)
- [ ] Relax to manual trigger only

#### Category 2: Code Quality Refactor Pass (Relaxable)
**Default**: Mandatory check for dead code, duplication, encapsulation

Options:
- [ ] Keep strict (always check) - Recommended
- [ ] Skip for hotfixes only
- [ ] Skip for documentation-only changes
- [ ] Disable (not recommended)

#### Category 3: Test Requirements (Relaxable)
**Default**: Tests must pass before marking complete

Options:
- [ ] Keep strict (tests required) - Recommended
- [ ] Allow WIP commits without tests
- [ ] Tests optional for prototypes

#### Category 4: Communication Standards (Relaxable)
**Default**: Factual language, no superlatives

Options:
- [ ] Keep strict - Recommended
- [ ] Relax for user-facing documentation
- [ ] Disable

#### Category 5: Tool Installation Policy (Relaxable)
**Default**: Always ask before installing

Options:
- [ ] Keep strict (always ask) - Recommended
- [ ] Auto-approve dev dependencies
- [ ] Auto-approve all (not recommended)

---

## NON-RELAXABLE Categories (Security)

These categories CANNOT be disabled but CAN be extended:

### Security Review Pass (MANDATORY - Extendable Only)
**Always enforced**: CVE scanning, OWASP Top 10 checks

Customization options (additive only):
- [ ] Add custom security rules (specify)
- [ ] Add additional CVE scanning tools
- [ ] Add custom anti-patterns to check
- [ ] Require security sign-off for specific file patterns

### Secrets Detection (MANDATORY - Extendable Only)
**Always enforced**: No hardcoded secrets

Customization options (additive only):
- [ ] Add custom secret patterns to detect
- [ ] Add file exclusions for false positives (with justification)

---

## Step 6: Environment Settings

Ask about project-specific environment:
- Python version requirements?
- Node.js version requirements?
- Required tools (linters, formatters)?
- CI/CD integration notes?

## Step 7: Generate Configuration

Based on user responses, generate a `.claude/CLAUDE.md` file with:

1. Header indicating it extends global config
2. **Selected Policies section** listing chosen policy modules
3. List of relaxed/modified rules with justification
4. Any additional rules or requirements
5. Environment-specific settings

### Template Structure

```markdown
# Project-Specific Guidelines: <project-name>

This file extends the global Ralph Wiggum configuration (`~/.claude/CLAUDE.md`).

---

## Selected Policies

Load the following policy modules from `~/.claude/policies/`:

- `<policy-path-1>`
- `<policy-path-2>`
- ...

---

## Project Overview

- **Type**: <Web app / CLI / Library / Service / etc.>
- **Language**: <Primary language>
- **Purpose**: <Brief description>

---

## Relaxed Rules

<!-- List any rules that are less strict than defaults -->

---

## Additional Rules

<!-- List any project-specific requirements -->

---

## Environment

<!-- Project-specific environment settings -->

---

## Security Extensions

<!-- Additional security requirements for this project -->

---

## Configuration Summary

| Category | Setting | Notes |
|----------|---------|-------|
| Validation Reports | <setting> | <notes> |
| Code Quality Checks | <setting> | <notes> |
| Test Requirements | <setting> | <notes> |
| Communication Style | <setting> | <notes> |
| Tool Installation | <setting> | <notes> |
| Policies | <list> | <notes> |
| Security | <setting> | <notes> |

---

*Generated by /ralph-setup on YYYY-MM-DD*
```

## Step 8: Confirm and Save

- Show the generated configuration to the user
- Ask for confirmation before saving
- Save to `.claude/CLAUDE.md` in the project root
- Remind user to commit the file

## Output

After setup is complete, summarize:
- What policies were selected
- What defaults were kept
- What was relaxed (with warnings if any)
- Next steps

$ARGUMENTS
