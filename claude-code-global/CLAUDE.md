# Global Development Guidelines (Ralph Wiggum Methodology)

This file establishes default development practices based on the Ralph Wiggum autonomous coding framework. Override or extend per-project via project-level `CLAUDE.md`.

---

## Core Philosophy

- **Spec-driven development**: Work from specifications with clear acceptance criteria
- **Iterative self-correction**: Handle one focused task per cycle
- **Test-based verification**: Tests enforce quality before marking work complete
- **Autonomous operation**: Make decisions, don't wait for approval on implementation details
- **Reversible by default**: Changes should be undoable in minutes without data heroics

---

## Release Safety Principles

AI coding tools let us produce more change per day. That increases release risk unless we build in reversibility.

**The question every release must answer:**
> "If this causes pain, can we undo it in minutes without data heroics?"

### Parallel Change: Expand, Migrate, Contract

Break risky changes into phases that stay compatible while different versions coexist:

| Phase | Action | Reversibility |
|-------|--------|---------------|
| **Expand** | Add new things without removing old ones | Full - just don't use new code |
| **Migrate** | Backfill and dual-write, then switch reads | Full - flip back to old reads |
| **Contract** | Remove old paths after confidence is established | Reduced - plan carefully |

**Key insight**: Changes stay additive during Expand and Migrate. Rollback becomes expensive only in Contract phase.

### Feature Flags for Release Control

Deploy code, then control exposure separately:
- **Deploy** = code is in production (can be instant)
- **Release** = behavior is enabled (can be gradual)

Use flags for:
- Behavior changes on existing endpoints
- Risky migrations during the Migrate phase
- Progressive rollout (internal → pilot → general)

### Stack-Specific Guidance

#### APIs (DRF/FastAPI/GraphQL)
- **Add fields, don't rename/remove in-place**. Ship old and new together until migration is complete.
- **Behavior changes require a flag**. Same endpoint, two behaviors, one rollback lever.
- **Version only when contracts must diverge**. Otherwise, control exposure with flags.

#### PostgreSQL / Database Migrations
- **Expand**: Add nullable columns, additive tables, use `CREATE INDEX CONCURRENTLY`
- **Migrate**: Backfill in batches, dual-write briefly, switch reads behind a flag
- **Contract**: Enforce constraints later, deprecate later, remove later (or never)

#### Elasticsearch / Search Indices
- Mappings often can't be changed in place - treat indices as versions
- Create new versioned index → Reindex → Switch with alias
- Rollback = flip alias back

#### Kubernetes / Container Deployments
- Release in rings: internal → pilot tenants → broader cohorts
- Canary or blue-green for high-risk changes
- Document the rollback lever: flag off, rollout undo, alias flip

### Concrete Example: Rename a Field

Want to rename `risk_score` to `threat_score`:

1. **Expand**: Add `threat_score` nullable, return both in API, UI reads old field
2. **Migrate**: Dual-write, backfill, flip reads behind flag (internal → pilot)
3. **Contract**: Stop dual-write, deprecate old field in future release

**Rollback at any point**: Flip the flag off - old path still works.

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

### Phase 4: Code Quality Refactor Pass
**Conditional refactoring** - Only refactor if issues are found:
- **Check for dead code**: Unused imports, unreferenced functions, unused variables, orphaned signals/events
- **Check for code duplication**: Repeated patterns, duplicate logic blocks, copy-pasted code
- **Check for poor encapsulation**: God classes, long methods (>50 lines), mixed responsibilities, tight coupling
- **Extract helper methods**: When the same pattern appears 2+ times
- **Verify tests still pass** after any refactoring

**Guidelines**:
- If no significant issues found, mark as passed and proceed
- Keep refactorings small and focused
- Never skip this step - code quality matters
- Commit refactorings separately with clear messages (e.g., "refactor: extract helper method for X")

### Phase 5: Security Review Pass
**Comprehensive security analysis** - Check for vulnerabilities and security anti-patterns:

#### Dependency Security
- **CVE Scanning**: Check for known vulnerabilities in dependencies
  - Python: Use `pip-audit` or `safety check`
  - Node.js: Use `npm audit` or `yarn audit`
  - Rust: Use `cargo audit`
- **Update vulnerable dependencies** to patched versions when available
- **Document any remaining vulnerabilities** with justification if not fixable

#### OWASP Top 10 Checks
1. **Injection**: Check for SQL injection, command injection, code injection vulnerabilities
   - Validate/sanitize all external input
   - Use parameterized queries, not string concatenation
   - Avoid `eval()`, `exec()`, shell=True in subprocess calls
2. **Broken Authentication**: Verify secure credential handling
   - No hardcoded passwords/API keys in code
   - Use secure session management
   - Implement proper password hashing (bcrypt, argon2)
3. **Sensitive Data Exposure**: Check for data leakage
   - No credentials in logs or error messages
   - Sensitive data encrypted at rest and in transit
   - No secrets in version control
4. **XML External Entities (XXE)**: Disable external entity processing in XML parsers
5. **Broken Access Control**: Verify authorization checks
   - Validate user permissions before operations
   - No reliance on client-side access control
6. **Security Misconfiguration**: Check for insecure defaults
   - No debug mode in production
   - Remove default credentials
   - Secure HTTP headers (CSP, HSTS, etc.)
7. **Cross-Site Scripting (XSS)**: Sanitize output in web contexts
   - Escape HTML/JavaScript in user-generated content
   - Use Content Security Policy
8. **Insecure Deserialization**: Validate serialized data
   - Don't deserialize untrusted data without validation
   - Use safe serialization formats (JSON over pickle)
9. **Using Components with Known Vulnerabilities**: See Dependency Security above
10. **Insufficient Logging & Monitoring**: Ensure security events are logged
    - Log authentication failures, access control violations
    - Don't log sensitive data

#### Code Security Anti-Patterns
- **Hardcoded secrets**: Check for API keys, passwords, tokens in source code
- **Unsafe file operations**: Path traversal vulnerabilities, insecure temp file usage
- **Insufficient input validation**: Missing sanitization, weak validation
- **Race conditions**: TOCTOU (Time-of-check-time-of-use) vulnerabilities
- **Insecure randomness**: Using `random` instead of `secrets` for security-sensitive operations

**Remediation Process**:
- If **minor issues** found: Fix directly and re-run validation tests
- If **major issues** found requiring refactoring: Loop back to Phase 4 (Refactor Pass)
- If **critical vulnerabilities** found: Stop and fix immediately before proceeding
- After **significant security fixes**: Re-run full validation suite (Phase 3)

**Guidelines**:
- Prioritize fixes: Critical > High > Medium > Low
- Document security decisions and trade-offs
- When in doubt about a potential vulnerability, err on the side of caution
- Commit security fixes separately with clear messages (e.g., "security: fix SQL injection in user query")

### Phase 5.5: Release Safety Review

**Reversibility check** - Verify changes can be safely rolled back:

#### For Schema/Database Changes
- [ ] Uses Expand-Migrate-Contract pattern (or justified exception)
- [ ] New columns are nullable or have safe defaults
- [ ] Indexes created with `CONCURRENTLY` where supported
- [ ] Backfill strategy defined for data migrations
- [ ] Rollback path documented

#### For API Changes
- [ ] Additive only (no breaking removals in same release)
- [ ] Behavior changes behind feature flag (if applicable)
- [ ] Backward compatible with existing clients
- [ ] Rollback = disable flag or revert deploy

#### For Search/Index Changes
- [ ] Using versioned indices with alias strategy
- [ ] Rollback = flip alias to previous index

#### For Infrastructure/Deployment
- [ ] Rollout rings defined (internal → pilot → general)
- [ ] Rollback lever documented (flag, undo, alias flip)
- [ ] No shared state that prevents independent rollback

#### Rollback Plan Documentation
Every change must have an answer to: "How do we undo this in minutes?"

| Change Type | Rollback Approach |
|-------------|-------------------|
| Code-only | Revert commit, redeploy |
| Feature flag | Disable flag |
| Schema (Expand phase) | Ignore new columns |
| Schema (Migrate phase) | Flip reads to old path |
| Schema (Contract phase) | ⚠️ May require restore - document carefully |
| Index change | Flip alias |

**Skip conditions**: This phase can be streamlined for:
- Documentation-only changes
- Test-only changes
- Changes to development tooling

### Phase 6: Record History & Validation Artifacts
- Document significant learnings and decisions
- Update `history/` folder if project uses one
- Keep notes for future context
- **Save validation results** as project artifacts for tracking quality over time

#### Validation Artifacts

After completing validation phases (3-5), save results to track quality trends:

**Location**: `validation-reports/` or `history/validation/` in the project root

**IMPORTANT - Location verification**:
- **For sub-projects**: Always place validation reports in the sub-project directory
  - Example: `game-desktop-creator/validation-reports/` NOT `validation-reports/`
  - Before saving, verify you're in the correct directory with `pwd`
- **For standalone projects**: Place in the repository root `validation-reports/`
- **Double-check**: After creating a report, confirm it's in the right location before committing

**When to save** (MANDATORY for code changes):
- **ALWAYS** before committing new or modified code
- After completing all quality gates (Phases 3-5)
- For significant milestones or releases

**IMPORTANT**: A validation report is REQUIRED before any commit that includes code changes. This ensures:
- Quality gates were actually run (not just claimed)
- Audit trail exists for compliance
- Issues are documented before they reach production

**What to include**:
```
validation-reports/YYYY-MM-DD-HHmm-<task-name>.md

## Validation Report: <Task/Feature Name>
**Date**: YYYY-MM-DD HH:MM
**Commit**: <git commit hash>
**Status**: PASSED/FAILED

### Phase 3: Tests
- Test suite: <test command>
- Results: X passing, Y failing
- Coverage: Z%
- Status: ✓ PASSED / ✗ FAILED

### Phase 4: Code Quality
- Dead code: None found / <issues>
- Duplication: None found / <issues>
- Encapsulation: Well-structured / <issues>
- Refactorings: <list any refactorings made>
- Status: ✓ PASSED / ✗ FAILED

### Phase 5: Security Review
- Dependencies: <tool> - X vulnerabilities (Critical: Y, High: Z)
- OWASP Top 10: <summary of findings>
- Anti-patterns: <summary>
- Fixes applied: <list>
- Status: ✓ PASSED / ✗ FAILED

### Phase 5.5: Release Safety
- Change type: Code-only / Schema / API / Infrastructure
- Pattern used: Expand-Migrate-Contract / Additive API / Feature flag / N/A
- Rollback plan: <describe how to undo in minutes>
- Rollout strategy: Immediate / Ringed (internal → pilot → general)
- Status: ✓ PASSED / ✗ FAILED / ⊘ SKIPPED (docs/tests only)

### Overall
- All gates passed: YES/NO
- Notes: <any additional context>
```

**Benefits**:
- Track quality trends over time
- Document due diligence for audits
- Identify recurring issues
- Demonstrate continuous improvement

### Phase 7: Commit & Complete

**Prerequisites** (must be true before committing):
- [ ] Validation report created and saved to `validation-reports/`
- [ ] All quality gates passed (Phases 3-5)
- [ ] Validation report committed alongside code changes

**Actions**:
- Mark spec as complete
- Commit with descriptive messages
- Deploy if applicable

**Note**: Never commit code changes without a corresponding validation report. The report documents that quality gates were actually executed.

---

## Git Preferences

- **No Co-Authored-By**: Do NOT include `Co-Authored-By` lines in commit messages
- Commit messages should be concise and descriptive
- Use conventional commit prefixes (feat, fix, chore, docs, refactor, test)

### Remote Connectivity Check
**Before running `git push`, `git pull`, or `git fetch`:**
- Test connectivity first with a short timeout: `timeout 5 git ls-remote --exit-code origin HEAD`
- If it fails or hangs, inform the user that the VPN may need to be manually bounced
- Only proceed with the actual git operation after connectivity is confirmed

### Phase 8: Completion Signal (Loop Mode Only)
Output `<promise>DONE</promise>` only when ALL of these pass:
- [ ] Requirements implemented
- [ ] Acceptance criteria met
- [ ] Tests passing
- [ ] Code quality refactored (if needed)
- [ ] Security reviewed and cleared
- [ ] Release safety reviewed (rollback plan documented)
- [ ] Validation report created and committed
- [ ] Changes committed
- [ ] Spec marked complete

---

## Writing and Communication Standards

All written artifacts (specs, documentation, commit messages, validation reports, code comments) should prioritize clarity and precision over style.

### Avoid Superlative and Marketing Language

**Prohibited words/phrases** - Use specific, factual alternatives:
- **Superlatives**: "amazing", "awesome", "excellent", "incredible", "fantastic"
- **Marketing fluff**: "enterprise-grade", "world-class", "cutting-edge", "next-generation", "industry-leading"
- **Vague quality claims**: "robust", "scalable", "performant", "reliable" (unless backed by metrics)

**Guidelines**:
- **Be factual and direct**: Describe what IS, not how impressive it is
- **Use concrete language**: "Handles 1000 req/sec" not "highly performant"
- **Quantify when possible**: "Reduces load time from 3s to 800ms" not "dramatically faster"
- **State capabilities clearly**: "Supports clustering via Redis" not "enterprise-grade scalability"

**Examples**:

| ❌ Avoid | ✅ Use Instead |
|---------|---------------|
| "This amazing feature provides enterprise-grade scalability" | "This feature supports horizontal scaling via Redis clustering" |
| "Awesome refactor that makes the code more robust" | "Refactor: extract database logic into repository pattern" |
| "Incredible test coverage improvements" | "Increase test coverage from 45% to 87%" |
| "World-class error handling implementation" | "Add retry logic with exponential backoff for API calls" |
| "Cutting-edge AI-powered optimization" | "Use TF-IDF vectorization for document similarity" |

**Purpose**: Written artifacts exist to communicate project status, requirements, and technical decisions clearly. Superlative and marketing language adds no information and obscures meaning.

---

## Tool and Package Installation

When you determine that a tool or package needs to be installed:

**STOP and ASK the user first** - Do NOT automatically install packages

**Why**: Installation is environment-specific and depends on:
- Operating system and package manager (apt, pacman, brew, dnf, etc.)
- Python installation type (system python, conda, virtualenv, pipx, etc.)
- User's environment preferences (some users avoid system-wide pip installs)
- Security and permission requirements

**Process**:
1. **Detect the need**: When a command fails because a tool is missing (e.g., `pip-audit`, `tree`, `rg`)
2. **Ask the user**:
   - "The tool X is not installed. Should I install it?"
   - If applicable: "Which method: [pip/apt/pacman/other]?"
3. **Wait for approval**: Do not proceed with installation without confirmation
4. **Document alternatives**: If the tool has a reasonable fallback, mention it

**Fallback strategies**:
- **If installation not approved**: Use reasonable defaults when available
  - Example: If `pip-audit` unavailable, skip CVE scanning but note it in validation report
  - Example: If `tree` unavailable, use `find` and `ls` alternatives
- **If no reasonable default exists**: Document the limitation clearly
  - Note what validation/functionality could not be completed
  - Include this in any validation reports or documentation

**Examples**:

❌ **Wrong approach**:
```
Tool not found. Installing via pip...
[proceeds with pip install without asking]
```

✅ **Correct approach**:
```
The pip-audit tool is not installed. This tool scans Python dependencies for known CVEs.

Options:
1. Install it: pipx install pip-audit (recommended)
2. Skip CVE scanning (will note this limitation in validation report)

Should I proceed with installation? [Provide installation command for your environment]
```

**Special cases**:
- **System tools** (apt, pacman): Always ask - these require sudo and modify system state
- **Python packages**: Ask which method (pip, pipx, conda) and where (system, venv)
- **Development tools**: Consider if they should be in requirements.txt instead

---

## Project-Specific Overrides

Per-project `CLAUDE.md` files can override these defaults by specifying:
- Custom spec locations
- Project-specific principles
- Different workflow phases
- Technology-specific guidelines
- Autonomy settings (YOLO mode, git autonomy, etc.)

### Customization Policy

**Philosophy**: Strict by default, relaxable by user, security is mandatory.

Use `/ralph-setup` for a guided wizard, or manually create `.claude/CLAUDE.md`.

#### Relaxable Guidelines
These can be loosened for specific projects:
- Validation report frequency (every commit → milestones only)
- Code quality refactor pass (always → skip for hotfixes)
- Test requirements (must pass → WIP commits allowed)
- Communication standards (strict → relaxed for docs)
- Tool installation policy (always ask → auto-approve dev deps)
- Git standards (partial: connectivity checks can be disabled)
- Release safety (full checklist → simplified → minimal for prototypes)

#### Non-Relaxable Guidelines (Security)
These CANNOT be disabled, only extended with additional rules:
- **Security Review Pass**: OWASP Top 10 checks, CVE scanning
- **Secrets Detection**: No hardcoded credentials in source

When relaxing guidelines, document the justification in the project config.

---

## Quick Reference

| Trigger | Mode | Behavior |
|---------|------|----------|
| `/ralph` command | Loop | Enter Loop Mode, work through specs autonomously |
| `ralph-loop.sh` | Loop | External orchestration with fresh context per iteration |
| Working through specs/ | Loop | Implement, test, signal completion |
| Conversation/questions | Interactive | Guide and collaborate |

---

## Keeping Global CLAUDE.md in Sync

**IMPORTANT**: This file (`claude-code-global/CLAUDE.md`) must stay in sync with the installed copy at `~/.claude/CLAUDE.md`.

**Whenever this file is updated**:
1. Copy changes to `~/.claude/CLAUDE.md` (or run `./install.sh`)
2. Commit the change to this project (claude-code-global)
3. This ensures the global methodology is tracked in version control

**Why**: This project serves as the canonical, version-controlled source for the Ralph Wiggum methodology that gets installed to `~/.claude/CLAUDE.md`.

---

## Notes

- Constitution file (`.specify/memory/constitution.md`) is the source of truth when present
- Always verify tests pass before marking anything complete
- Prefer working directly from specs over creating separate planning documents
- Commit frequently with meaningful messages
