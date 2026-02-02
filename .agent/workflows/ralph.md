---
description: The Ralph Wiggum Methodology. Spec-driven, iterative, and verifiable. Enforces fresh context and release safety.
---

# Ralph Wiggum Methodology (ag-scripts)

This workflow merges the global Ralph Wiggum principles with ag-scripts project specifics.

## Core Philosophy
- **Spec-Driven**: Work from `task.md` with clear acceptance criteria.
- **Fresh Context**: Iterations are stateless; persist progress to disk (`task.md`).
- **Release Safety**: "Can we undo this in minutes?"
- **Observability**: **CRITICAL**. If it doesn't log, it doesn't exist.

---

## Phase 1: Orient & Plan (Planning Mode)

1. **Check Task Context**:
   - Read `task.md`. If missing, CREATE it.
   - **Fresh Context**: If resuming, verify current state.
   - Using `task_boundary`: Set Mode to **PLANNING**.

2. **Select Work Item**:
   - Pick ONE focused task from `task.md`.
   - If complex, CREATE/UPDATE `implementation_plan.md`.
   - **Release Safety**: Plan `Expand-Migrate-Contract` for DB/API.

3. **Sub-Project Check**:
   - Identify the sub-project directory (e.g., `game-desktop-creator/`).
   - verify `tests/` directory exists.
   - verify `install.sh` and `uninstall.sh` exist (create minimal if missing).

---

## Phase 2: Implement (Execution Mode)

4. **Set Context**:
   - Using `task_boundary`: Set Mode to **EXECUTION**.
   - Mark `task.md` item as `[/]`.

5. **Clean Slate**:
   - **Kill Processes**: `pkill -f <script_name>` (ensure fresh logs).
   - **Clear Logs**: Remove old debug logs.

6. **Observability Check**:
   - **Before modification**: Does it log to stdout/stderr? Supports `--debug`?
   - **Action**: Add print/logging statements FIRST if missing.

7. **Implementation Loop**:
   - Implement the feature/fix.
   - **Artifacts**: Do NOT generate images unless asked.
   - **Environment**: Use system python (`/usr/bin/python`), NOT conda.

---

## Phase 3: Validate (Verification Mode)

8. **Set Context**:
   - Using `task_boundary`: Set Mode to **VERIFICATION**.

9. **Quality Gates (Mandatory)**:
   - **Tests**: Run `pytest` in `tests/` subdirectory. All must pass.
   - **Code Quality**: Check for dead code, duplication, poor encapsulation.
   - **Security**: Check for secrets, new dependencies.

10. **Manual Verification**:
    - Prove "Acceptance Criteria" are met.
    - Create `walkthrough.md`.
    - **Observability**: Verify logs contain useful info.

11. **Release Safety**:
    - Verify rollback plan (feature flags, migration steps).

---

## Phase 4: Finalization & Completion

12. **Documentation & scripts**:
    - **Props**: Update sub-project `README.md` (Version, Features, TOC).
    - **Changelog**: Add entry if exists.
    - **Scripts**: Update `install.sh` and `uninstall.sh` if artifacts changed.
    - **Global**: Update root `README.md` list of scripts.

13. **Commit**:
    - [ ] Validation Report (`walkthrough.md`) created.
    - [ ] `task.md` Updated (`[x]`).
    - [ ] Commit with conventional message. NO `Co-Authored-By`.

14. **Completion**:
    - `notify_user` with success and `walkthrough.md`.

---

## Anti-Patterns
- **Indefinite Loops**: Don't spin forever. Stop and ask.
- **Hidden State**: Don't rely on memory; use `task.md`.
- **Blind Execution**: Never run without logging.
