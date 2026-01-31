---
description: Spec-driven iterative development with fresh context, quality gates, and natural convergence.
---

## Core Philosophy

Wiggum is an agentic development workflow based on three principles:

1. **Fresh Context Each Iteration** - Spawn a new agent process per task to prevent context degradation
2. **Spec-Driven Development** - Clear specifications with testable acceptance criteria
3. **Backpressure Via Tests** - Tests, builds, and lints act as quality gates that must pass before proceeding

---

## Phase 1: Specification

Before any implementation, establish clear requirements:

*   **Define Requirements**: What specific functionality is being added or fixed?
*   **Acceptance Criteria**: List testable conditions that prove the work is complete
    *   Good: "Login form validates email format and shows error message within 200ms"
    *   Bad: "Login should work better"
*   **Write Tests First**: Create failing tests that encode the acceptance criteria
    *   Write tests in pytest, kept in a `tests/` subdirectory of the project
    *   Tests act as executable specifications

---

## Phase 2: Planning Mode

Compare specifications against existing code and create a prioritized task list:

*   **Analyze Current State**: Read existing code, understand the architecture
*   **Gap Analysis**: What's missing between current state and specification?
*   **Create Plan File**: Write a `PLAN.md` (or similar) with:
    *   Prioritized task list (one task per item)
    *   Each task should be completable in a single iteration
    *   Clear definition of done for each task
*   **Shared State on Disk**: The plan file persists between iterations—this is how context transfers between fresh agent sessions

---

## Phase 3: Build Mode

Each iteration handles ONE task—implement, test, commit, then exit:

### 3.1 Preparation

*   **Read Plan File**: Identify the next incomplete task
*   **Ensure Observability**:
    *   Does the program output logs to stdout/stderr?
    *   Does it support a `--debug` flag? Use it.
    *   **CRITICAL**: If the program lacks logging, add print/logging statements first. Do not skip this.
*   **Environment Check**: For Python scripts, use system python (`/usr/bin/python` or `/usr/bin/python3`), NOT conda/miniforge environments.
*   **Artifact Restriction**: Do NOT generate artifacts (especially images) unless explicitly requested. Focus on code and logs.

### 3.2 Clean Slate

*   **Kill Existing Instances**: Before every run, kill any background instances or GUI processes (e.g., `pkill -f my_script.py`) to ensure fresh log capture.

### 3.3 Implementation

*   **Single Task Focus**: Implement ONLY the current task from the plan
*   **Run & Capture**: Execute with logging enabled
    *   For long-running processes: `timeout 30 python3 script.py --debug > debug.log 2>&1`
*   **Quality Gates** (ALL must pass before proceeding):
    *   [ ] Tests pass
    *   [ ] Build succeeds
    *   [ ] Lints clean (if applicable)
*   **If Gates Fail**: Fix issues in this iteration—do NOT proceed with flawed work

### 3.4 Commit & Exit

*   **Commit**: Make a focused commit for this single task
*   **Update Plan File**: Mark task complete, note any discoveries or blockers
*   **Clean Up**: Remove temporary logs and debug files
*   **Exit**: End this iteration. A fresh context will handle the next task.

---

## Phase 4: Finalization

When all tasks in the plan are complete:

*   **Update Sub-project Docs & Version** (Reference: `/update_docs_and_version`):
    *   **Identify Sub-Project**: Locate main source and README.
    *   **Bump Version**: Increment version in source code and README.
    *   **Update README**: Add new features/fixes to the sub-project's README.
    *   **Update Inline Help** (If applicable): Ensure any internal help text, "About" dialog content, or `--help` output reflects new changes and the updated version.
    *   **Update Changelog**: If the README has a `## Changelog` section, add an entry for the new version summarizing changes.
*   **Ensure Installer**:
    *   Check if `install.sh` exists.
    *   If not, create one (even if minimal) to maintain consistency.
*   **Ensure Uninstaller** (Reference: `/uninstaller`):
    *   Check if `uninstall.sh` exists.
    *   If not, create one that removes desktop files, config entries, etc.
    *   If yes, update it to include any new artifacts.
*   **Update Global Documentation** (Reference: `/update_documentation`):
    *   Identify all scripts in the repo.
    *   Update the root `README.md` with a table/list of all scripts and their descriptions.
*   **Final Test Run**: Run full test suite to confirm nothing regressed
*   **Notify User**: Confirm success and documentation updates.

---

## Anti-Patterns to Avoid

| Anti-Pattern | Why It's Bad | Do This Instead |
|--------------|--------------|-----------------|
| Indefinite single-session loops | Context overflow, lossy compaction, stale reasoning | Fresh context per iteration |
| Vague success criteria | No way to know when done | Testable acceptance criteria |
| Skipping failing tests | Technical debt accumulates | Fix before proceeding |
| Multi-task iterations | Scope creep, partial completions | One task per iteration |
| In-memory state only | Lost on session end | Persist state to plan file |

---

## Quick Reference

```
# Planning mode
1. Write specification with acceptance criteria
2. Create failing tests
3. Generate PLAN.md with prioritized tasks

# Build mode (repeat per task)
1. Read PLAN.md → identify next task
2. Clean slate (kill old processes)
3. Implement single task
4. Pass all quality gates (tests, build, lint)
5. Commit → Update PLAN.md → Exit

# Finalization
1. Update docs & version
2. Ensure install/uninstall scripts
3. Full test suite
4. Notify user
```