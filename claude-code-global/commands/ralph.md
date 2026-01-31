---
description: Activate Ralph Loop autonomous development mode
argument-hint: [optional-context]
---

# Ralph Loop Mode Activation

You are now entering **Ralph Loop Mode**. Follow the Ralph Wiggum autonomous development methodology.

## Your Mission

Work through the project's specs autonomously. For each incomplete spec:

1. **Orient** - Read `.specify/memory/constitution.md` (if exists) and review specs in `specs/`
2. **Select** - Choose the lowest-numbered incomplete spec (no "Status: COMPLETE")
3. **Implement** - Code the spec completely, following requirements precisely
4. **Validate** - Run tests, verify acceptance criteria are met
5. **Record** - Document learnings in `history/` if the project uses one
6. **Commit** - Mark spec complete, commit with descriptive message

## Completion Signal

When ALL of the following are true, output `<promise>DONE</promise>`:
- [ ] Requirements implemented
- [ ] Acceptance criteria met (all boxes checked)
- [ ] Tests passing
- [ ] Changes committed
- [ ] Spec marked "Status: COMPLETE"

## Rules

- **One spec per iteration** - Don't try to do multiple specs
- **No partial completion** - Either fully complete the spec or explain what's blocking
- **Tests are gates** - If tests fail, fix them before marking complete
- **Be autonomous** - Make implementation decisions, don't ask for approval on details

## Getting Started

First, list the specs in `specs/` and identify incomplete ones. Then begin work on the first incomplete spec.

If there are no specs or all specs are complete, report the status and await further instructions.

$ARGUMENTS
