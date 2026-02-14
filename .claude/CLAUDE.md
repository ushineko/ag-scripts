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

## TodoWrite for Workflow Tracking (REQUIRED)

Use the TodoWrite tool to visibly track progress on any multi-phase workflow. This ensures no steps are skipped and provides accountability.

**When to use TodoWrite**:
- Any workflow with 3+ steps
- Finalization passes (all steps must be visible)
- Ralph loop iterations
- Bug fix batches

**How to use**:
1. Before starting work, create todos for ALL steps in the workflow
2. Mark each step `in_progress` when starting it
3. Mark each step `completed` only when fully done
4. Never commit until all todos are checked off

**Example for finalization pass**:
```
☐ Run tests
☐ Code quality pass
☐ Security review
☐ Update docs & version
☐ Ensure installer
☐ Ensure uninstaller
☐ Update root README
☐ Create validation report
☐ Commit changes
```

**Why this matters**: Visual tracking prevents steps from being skipped. If "Create validation report" is sitting unchecked when you're about to commit, it's an obvious signal that something was missed.

---

## Finalization Phase

When completing work on a sub-project:

### 1. Update Sub-project Docs & Version

**Identify and Update Version**:
- Locate main source file and README in the sub-project
- Search for version strings using grep (look for `__version__`, `vX.Y`, or text in "About" dialogs)
- Determine the current version and propose a new version (e.g., 1.0 -> 1.1, or 10.0 -> 11.0 for major changes)
- **ASK THE USER** to approve the proposed version or provide their own version number
- Update version in BOTH source code AND README only after user approval
- Verify consistency: version in source must match README

**Update README.md**:
- **Version**: Update any mentions of the version number
- **Features**: Add bullet points for newly implemented features under "Features" or "Changelog" section
- **Usage**: Update usage examples if CLI arguments or behavior changed
- **Changelog**: If the README has a `## Changelog` section, add an entry for the new version
- **TOC**: All project READMEs should have a Table of Contents after the title/description

**Update Help Text**:
- Update inline help text, "About" dialogs, or `--help` output if applicable

### 2. Ensure Installer
- Check if `install.sh` (or `install.bat` for Windows) exists in the sub-project
- If not, create one (even if minimal) for consistency

### 3. Ensure Uninstaller

**Check for Existing Uninstaller**:
- Look for `uninstall.sh`, `uninstall.bat`, or `remove.sh` in the project root

**Define Cleanup Scope** (common items to remove):
- `.desktop` files in `~/.local/share/applications/`
- KWin rules in `~/.config/kwinrulesrc`
- Symlinks in `~/bin` or `/usr/local/bin`
- Systemd user units in `~/.config/systemd/user/`
- Cron jobs and autostart entries
- Config files in `~/.config/` or `%APPDATA%`

**Create/Update Script**:
- If no script exists, create `uninstall.sh` (or `.bat` for Windows)
- Script should be idempotent (use `rm -f`, check if files exist before deleting)
- Print clear messages ("Removing X...", "Done.")
- Make executable: `chmod +x uninstall.sh`

### 4. Update Global Documentation

**Root README.md**:
- Identify all script files (Python, Shell, etc.) in the repository, including subdirectories
- Extract a brief description for each script (from docstrings, comments, or --help output)
- Update the root `README.md` with a "Scripts" or "Projects" section
- Format as a table or detailed list with columns: Script Name/Path, Description
- Preserve any existing manual documentation

### 5. Code Quality Refactor Pass
**Conditional refactoring** - Only refactor if issues are found:
- **Check for dead code**: Unused imports, unreferenced functions, unused signals/events
- **Check for code duplication**: Repeated patterns, duplicate logic blocks
- **Check for poor encapsulation**: God classes, long methods (>50 lines), mixed responsibilities
- **Extract helper methods**: When the same pattern appears 2+ times
- **Verify tests still pass** after any refactoring

**Guidelines**:
- If no significant issues found, mark as passed and proceed
- Keep refactorings small and focused
- Never skip this step - code quality matters
- Commit refactorings separately with clear messages

### 6. Final Test Run
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
| Multi-step workflow without TodoWrite | Create visible checklist first |

---

## Sub-project Structure Reference

Each sub-project should have:
```
sub-project/
├── README.md          # Sub-project documentation
├── install.sh         # Installer script (install.bat for Windows)
├── uninstall.sh       # Uninstaller script (uninstall.bat for Windows)
├── tests/             # pytest tests
└── [source files]
```

---

## KDE Plasma / Wayland Patterns

### Always-on-Top Windows

`Qt.WindowType.WindowStaysOnTopHint` is NOT reliably honored on KDE Plasma Wayland (QTBUG-73456). Use the belt-and-suspenders approach:

1. Set the Qt hint in the constructor (works as fallback on non-KDE)
2. Ship an `install_kwin_rule.py` that writes to `~/.config/kwinrulesrc`:
   - `above=true` / `aboverule=2` (Force keep-above at compositor level)
   - Match by `wmclass` (set via `app.setDesktopFileName()`)
3. Trigger reload: `qdbus6 org.kde.KWin /KWin reconfigure`
4. Uninstaller removes the rule with `--uninstall` flag

Reference implementations: `peripheral-battery-monitor/install_kwin_rule.py`, `alacritty-maximizer/install_kwin_rules.py`, `foghorn-leghorn/install_kwin_rule.py`

### KWin Rule Values

- `2` = Force (compositor enforces regardless of app behavior)
- `4` = Apply Initially (set on window creation, user can override)

### Tools That Do NOT Work on Wayland

`xdotool`, `wmctrl`, `xprop`, `xwininfo` - all X11 only. Use KWin rules or D-Bus instead.

---

## System Integration: Prefer Stable Contracts

When interfacing with system services (BlueZ, NetworkManager, PulseAudio, etc.), prefer stable programmatic interfaces over CLI tools:

| Approach | Stability | Example |
| -------- | --------- | ------- |
| D-Bus interfaces | Stable contract, versioned | `org.bluez.Device1`, `org.freedesktop.NetworkManager` |
| Library bindings | Stable, typed | `python-dbus`, `pydbus`, GLib/GIO |
| JSON-output CLI | Moderate (structured output) | `pactl --format=json`, `nmcli -t` |
| Human-readable CLI | Brittle (output changes between versions) | `bluetoothctl`, `nmcli` (default format) |

**Why**: CLI tools are user-facing — their output format, behavior in interactive vs non-interactive mode, and even subcommand semantics can change between minor versions without notice (e.g., bluez 5.86 broke `bluetoothctl devices` in non-interactive mode). D-Bus interfaces are the stable programmatic API that desktop environments and audio stacks themselves depend on.

**Guidelines**:

- Use D-Bus for any daemon that exposes one (BlueZ, NetworkManager, UPower, systemd, KWin)
- When D-Bus isn't available, prefer CLI tools with structured output (`--format=json`, `-t` for terse)
- If you must parse human-readable CLI output, treat it as fragile and document the assumption
- `pactl --format=json` is acceptable — PulseAudio/PipeWire's JSON output is a supported interface

---

## Workflow References

Additional workflow guidance available in `.agent/workflows/`:
- `update_documentation.md` - Root README update procedures
- `update_docs_and_version.md` - Sub-project versioning and docs
- `uninstaller.md` - Uninstaller creation guidelines
- `base.md` - Core Ralph Wiggum methodology workflow
