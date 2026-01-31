# ag-scripts Project Guidelines

This project follows the Ralph Wiggum methodology (see `~/.claude/CLAUDE.md` for global defaults) with the following project-specific extensions.

---

## Project Overview

A collection of utility scripts and tools for Linux desktop automation, system configuration, and quality-of-life improvements. Each sub-directory is a self-contained project.

---

## Environment Requirements

- **Python**: Use system python (`/usr/bin/python` or `/usr/bin/python3`), NOT conda/miniforge environments
- **Tests**: pytest, kept in a `tests/` subdirectory of each sub-project
- **Artifacts**: Do NOT generate artifacts (especially images) unless explicitly requested

---

## Observability (CRITICAL)

Before running any script:
1. Check if it outputs logs to stdout/stderr
2. Check for `--debug` flag support - use it if available
3. **If logging is missing, add print/logging statements first** - do not skip this

For long-running processes:
```bash
timeout 30 python3 script.py --debug > debug.log 2>&1
```

---

## Clean Slate Rule

Before every run, kill any background instances or GUI processes to ensure fresh log capture:
```bash
pkill -f my_script.py
```

---

## Quality Gates

ALL must pass before proceeding to next task:
- [ ] Tests pass
- [ ] Build succeeds (if applicable)
- [ ] Lints clean (if applicable)

If gates fail, fix issues in the current iteration - do NOT proceed with flawed work.

---

## Finalization Phase

When completing work on a sub-project:

### 1. Update Sub-project Docs & Version
- Locate main source and README in the sub-project
- Increment version in source code and README
- Update README with new features/fixes
- Update inline help text, "About" dialogs, or `--help` output if applicable
- **Update Changelog**: If the README has a `## Changelog` section, add an entry for the new version with a summary of changes

### 2. Ensure Installer
- Check if `install.sh` exists in the sub-project
- If not, create one (even if minimal) for consistency

### 3. Ensure Uninstaller
- Check if `uninstall.sh` exists
- If not, create one that removes desktop files, config entries, etc.
- If yes, update it to include any new artifacts

### 4. Update Global Documentation
- Update the root `README.md` with table/list of all scripts and descriptions

### 5. Final Test Run
- Run full test suite to confirm nothing regressed

---

## State Persistence

- **Plan files**: Use `PLAN.md` in the sub-project directory to track multi-task work
- Plan file persists between iterations - this is how context transfers between fresh sessions
- Mark tasks complete and note discoveries/blockers as you go

---

## Anti-Patterns to Avoid

| Anti-Pattern | Do This Instead |
|--------------|-----------------|
| Indefinite single-session loops | Fresh context per iteration |
| Vague success criteria | Testable acceptance criteria |
| Skipping failing tests | Fix before proceeding |
| Multi-task iterations | One task per iteration |
| In-memory state only | Persist state to plan file |

---

## Sub-project Structure Reference

Each sub-project should have:
```
sub-project/
├── README.md          # Sub-project documentation
├── install.sh         # Installer script
├── uninstall.sh       # Uninstaller script
├── tests/             # pytest tests
└── [source files]
```
