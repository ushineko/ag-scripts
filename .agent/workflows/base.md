---
description: The default project workflow based on Ralph Wiggum Methodology. Enforces spec-driven development, release safety, and rigorous verification.
---

# Base Workflow (Ralph Wiggum Methodology)

This workflow defines the standard operating procedure for all development tasks. It prioritizes reversibility, specific acceptance criteria, and comprehensive validation.

## Core Philosophy
- **Spec-driven**: Work from `task.md` or `implementation_plan.md` with clear acceptance criteria.
- **Iterative**: Handle one focused task per cycle.
- **Backpressure**: Tests and lints are quality gates that MUST pass.
- **Reversible**: Changes should be undoable in minutes (Expand-Migrate-Contract).

---

## Phase 1: Orient & Plan (Planning Mode)

1. **Check Task Context**:
   - Read `task.md` to identify the current objective.
   - If `task.md` does not exist or is empty, CREATE it with a breakdown of the work.
   - Using `task_boundary` tool: Set Mode to **PLANNING**.

2. **Select Work Item**:
   - Pick the next uncompleted item from `task.md`.
   - If the task is complex (>3 files or API changes), CREATE or UPDATE `implementation_plan.md`.
   - **Release Safety Check**: If changing DB schema or APIs, verify the plan uses **Expand-Migrate-Contract**.

3. **User Review**:
   - If `implementation_plan.md` was created, use `notify_user` to request review.
   - Wait for approval before proceeding to implementation.

---

## Phase 2: Implement (Execution Mode)

4. **Set Context**:
   - Using `task_boundary` tool: Set Mode to **EXECUTION**.
   - Update `task.md` to mark item as `[/]` (in progress).

5. **Implementation Loop**:
   - Implement the feature/fix.
   - **Context Freshness**: If the task takes too long, stop and checkpoint.
   - **Feature Flags**: Put risky changes behind flags (as per `CLAUDE.md`).

---

## Phase 3: Validate (Verification Mode)

6. **Set Context**:
   - Using `task_boundary` tool: Set Mode to **VERIFICATION**.

7. **Automated Verification**:
   - **Run Tests**: Execute the project's test suite. `pytest`, `npm test`, etc.
   - **Lint**: Run linters. Fix *all* errors.
   - **Security Check**:
     - Check for hardcoded secrets.
     - Check for new dependencies (ask user before adding).

8. **Manual Verification**:
   - Verify the "Acceptance Criteria" from Phase 1 are met.
   - Create `walkthrough.md` in `brain/` or `validation-reports/`.
     - Include: Changes made, Tests run, Validation results.
     - Embed screenshots or recordings if UI was changed.

9. **Release Safety Verification**:
   - If DB/API change: Confirm rollback plan is documented in `walkthrough.md`.

---

## Phase 4: Commit & Complete

10. **Pre-Commit Checks**:
    - [ ] Tests passed?
    - [ ] Lints clean?
    - [ ] `walkthrough.md` created?
    - [ ] Security checks passed?

11. **Commit**:
    - `git commit` with a concise, conventional message (feat, fix, refactor).
    - **No Co-Authored-By** lines.

12. **Update Task State**:
    - Mark item as `[x]` in `task.md`.
    - Update `task_boundary` status.

13. **Loop or Exit**:
    - If more tasks remain, return to Phase 1.
    - If done, `notify_user` with a summary and link to `walkthrough.md`.
