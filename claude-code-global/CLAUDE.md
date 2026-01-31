# Global Development Guidelines (Ralph Wiggum Methodology)

This file establishes default development practices based on the Ralph Wiggum autonomous coding framework. Override or extend per-project via project-level `CLAUDE.md`.

---

## Core Philosophy

- **Spec-driven development**: Work from specifications with clear acceptance criteria
- **Iterative self-correction**: Handle one focused task per cycle
- **Test-based verification**: Tests enforce quality before marking work complete
- **Autonomous operation**: Make decisions, don't wait for approval on implementation details

---

## Context Detection

### Ralph Loop Mode (Automated Workflow)
Triggered when:
- Running via `ralph-loop.sh` or similar orchestration
- Prompt references "implement spec" or completion signals
- Working through a `specs/` folder systematically

**Behavior**: Focus purely on implementation. Output `<promise>DONE</promise>` only when all acceptance criteria pass.

### Interactive Mode (Default)
When user is asking questions, discussing ideas, or working conversationally.

**Behavior**: Provide guidance, explain decisions, and collaborate on specs/planning.

---

## Implementation Workflow

When working on features/tasks, follow these phases:

### Phase 0: Orient
- Read project constitution (`.specify/memory/constitution.md`) if it exists
- Review any specs in `specs/` folder
- Understand project principles and constraints

### Phase 1: Select Work Item
- Identify incomplete specs (unchecked criteria, no "Status: COMPLETE")
- Prioritize lower-numbered specs first
- If a task has failed 10+ attempts, suggest splitting into simpler tasks

### Phase 2: Implement
- Code the selected spec completely
- Follow requirements precisely
- Add tests for new functionality

### Phase 3: Validate
- Confirm all existing tests pass
- Verify new functionality meets acceptance criteria
- Run the full test suite

### Phase 4: Record History
- Document significant learnings and decisions
- Update `history/` folder if project uses one
- Keep notes for future context

### Phase 5: Commit & Complete
- Mark spec as complete
- Commit with descriptive messages
- Deploy if applicable

---

## Git Preferences

- **No Co-Authored-By**: Do NOT include `Co-Authored-By` lines in commit messages
- Commit messages should be concise and descriptive
- Use conventional commit prefixes (feat, fix, chore, docs, refactor, test)

### Phase 6: Completion Signal (Loop Mode Only)
Output `<promise>DONE</promise>` only when ALL of these pass:
- [ ] Requirements implemented
- [ ] Acceptance criteria met
- [ ] Tests passing
- [ ] Changes committed
- [ ] Spec marked complete

---

## Project-Specific Overrides

Per-project `CLAUDE.md` files can override these defaults by specifying:
- Custom spec locations
- Project-specific principles
- Different workflow phases
- Technology-specific guidelines
- Autonomy settings (YOLO mode, git autonomy, etc.)

---

## Quick Reference

| Trigger | Mode | Behavior |
|---------|------|----------|
| `/ralph` command | Loop | Enter Loop Mode, work through specs autonomously |
| `ralph-loop.sh` | Loop | External orchestration with fresh context per iteration |
| Working through specs/ | Loop | Implement, test, signal completion |
| Conversation/questions | Interactive | Guide and collaborate |

---

## Notes

- Constitution file (`.specify/memory/constitution.md`) is the source of truth when present
- Always verify tests pass before marking anything complete
- Prefer working directly from specs over creating separate planning documents
- Commit frequently with meaningful messages
