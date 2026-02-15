# Release Safety: Simplified

> **Policy module**: Activated via `## Selected Policies` in project `.claude/CLAUDE.md`.
> For internal tools and non-critical services where formal release checklists are unnecessary.

---

## Core Principle

Every change should be reversible. Document how, but skip the formal checklists.

## Requirements

- **Document the rollback approach** in commit messages or PR descriptions when the change affects behavior
- **Prefer additive changes** — add new things before removing old ones
- **Standard git revert** is sufficient rollback for most changes in this project category

## When to Escalate

If a change involves any of the following, consider using the `release-safety/full.md` policy instead:
- Database schema changes in production
- API contract changes consumed by external clients
- Infrastructure changes affecting multiple services
