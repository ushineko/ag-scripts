# Global Development Guidelines (Ralph Wiggum Methodology)

This file establishes default development practices based on the Ralph Wiggum autonomous coding framework. Override or extend per-project via project-level `CLAUDE.md`.

Language-specific standards, git workflows, release safety details, and external tool integrations are defined in policy modules. See [Policy Module System](#policy-module-system) below.

---

## Core Philosophy

- **Spec-driven development**: Work from specifications with clear acceptance criteria
- **Iterative self-correction**: Handle one focused task per cycle
- **Test-based verification**: Tests encode behavioral contracts, not just coverage checkboxes
- **Human-in-the-loop by default**: AI accelerates implementation; humans own design decisions and convergence. Surface choices early rather than presenting finished work for bulk review
- **Reversible by default**: Changes should be undoable in minutes without data heroics

---

## AI Tool Input Hygiene

AI coding tools send repository context to third-party APIs. This is how they work. Managing what they see is as important as reviewing what they produce.

### The Input/Output Risk Model

| Risk | Question | Where Ralph Addresses It |
|------|----------|--------------------------|
| **Input** | What data reaches the AI provider? | Context exclusion (below) |
| **Output** | Did the AI produce safe, correct code? | Phases 3-5 (test, quality, security) |
| **Display** | What credentials appear in the terminal? | Credential display safety (below) |

Ralph's workflow handles output risk thoroughly. Input risk and display risk require these additional practices.

### Context Exclusion

Ensure sensitive files never enter the AI tool's context window:

- **`.gitignore`** — AI tools generally respect this. Verify it covers: `.env*`, `*.pem`, `*.key`, `credentials.*`, and any private data directories.
- **`.claudeignore`** / **`.cursorignore`** — Tool-specific exclusion files. Mirror your `.gitignore` patterns and add anything sensitive that's tracked in git (e.g., configuration with internal URLs, proprietary datasets).
- **Secrets in code** — Phase 5 catches these before commit, but they also represent input risk while you're working. Prefer environment variables and secret managers over any in-repo secrets.

### Credential Display Safety

AI tools construct and execute shell commands on your behalf. When those commands involve authentication, credentials can appear in the terminal UI — in the command preview, in command output, or in shell history. This is a concern during screensharing, pair programming, or recorded sessions.

**Where credentials become visible:**
- **Command preview**: AI tools show the full command before execution. A `curl -H "Authorization: Bearer sk-abc123"` exposes the token in the UI.
- **Command output**: Some tools echo auth details in verbose or debug output.
- **Terminal scrollback**: Credentials persist in scroll history after the command finishes.
- **Shell history**: Commands with literal tokens get saved to `~/.bash_history` or `~/.zsh_history`.

**Prefer authentication methods that keep credentials out of commands:**

| Approach | Credential Visibility | Example |
|----------|----------------------|---------|
| MCP server with config-based auth | Not visible — auth in server config | Token in MCP config file, never in commands |
| CLI with built-in auth (gh, kubectl) | Not visible — auth in config file | Token in `~/.config/`, not in commands |
| `curl` with `--netrc-file` | Not visible — auth in netrc file | Credentials in `~/.netrc`, not in command |
| Environment variable in command | **Visible if expanded** | `$TOKEN` may appear as literal value in output |
| Literal token in command | **Fully visible** | Worst case — avoid this pattern |

**Prompt before exposing credentials:**

When about to execute a command that would include a credential in plaintext (e.g., a token in a `curl` header, an API key as a CLI argument), **stop and ask the user before constructing the command**. Do not write the command first and then ask — the credential would already be visible in the terminal at that point.

- Describe what you intend to do and why it requires a credential (e.g., "I need to call the API to check status. This would require passing your token as a header.")
- Give the user the chance to: approve, suggest a safer alternative (MCP server, authenticated CLI), or cancel
- If the user approves credential-bearing commands for the session, do not prompt again for the same type of operation. Treat it as a session-level permission

**For day-to-day work:**
- Instruct the AI tool to reference environment variables rather than reading and embedding literal token values into commands
- MCP servers are the safest pattern for tool integrations — auth is configured once in the server config and never appears in any command
- Authenticated CLIs (gh, kubectl) are the next safest — they read from their own config files
- Avoid patterns where the AI reads a token from a file and interpolates it into a `curl` command

---

## Test Philosophy

AI tools can produce tests rapidly, but speed of test creation is not the same as quality of test design. Tests encode commitments about system behavior. The wrong tests create maintenance burden without meaningful safety.

> Influenced by Abel Enekes, ["When Change Becomes Cheaper Than Commitment"](https://www.abelenekes.com/when-change-becomes-cheaper-than-commitment) (2026), which applies Khalil Stemmler's divergence/convergence model to AI-assisted development.

### Tests Are Contracts, Not Coverage

Every test is an implicit contract: "the system must continue to behave this way." The value of that contract depends on what it commits to and how long that commitment lasts.

| Contract Type | Example | Lifespan | Refactor Survival | Value |
|---------------|---------|----------|-------------------|-------|
| **User-facing behavioral** | "Login returns a session token" | Long — tied to product promises | High — survives internal rewrites | High |
| **Integration boundary** | "Service A calls Service B with correct payload" | Medium — tied to API contracts | Medium — survives internal changes | Medium |
| **Implementation detail** | "Function X calls mock Y with args Z" | Short — tied to current code structure | Low — breaks on any refactor | Low unless isolating specific logic |

**Prioritize long-lived contracts.** Tests that verify what the system does for users survive architectural changes. Tests that verify how the code is internally wired break when you refactor.

### The "Mock the Universe" Anti-Pattern

If a test requires mocking many dependencies to achieve isolation, that is a signal — either the code under test has too many dependencies (refactor the code) or you are testing at the wrong level of abstraction (move the test higher).

**Symptoms**:
- Test setup is longer than the test itself
- Mocks encode internal call sequences and argument shapes
- Changing one function's implementation breaks tests for unrelated features
- Test suite resists refactoring rather than enabling it

**Guidance**:
- Use mocks sparingly and deliberately, not as the default approach
- Prefer testing through public interfaces and real collaborators where practical
- When mocks are necessary, mock at architectural boundaries (external APIs, databases, third-party services), not between internal modules
- If you find yourself mocking more than 2-3 dependencies for a single test, reconsider the test's abstraction level

### Coverage Measures Exercise, Not Intent

Coverage tells you which code paths were executed during tests. It does not tell you whether those tests encode meaningful commitments. A 95% coverage number built on heavily-mocked unit tests may provide less real safety than 60% coverage built on integration tests that verify actual behavior.

**Guidance**:
- Do not treat coverage as a target to maximize. Treat it as a diagnostic — low coverage in critical paths is a signal; high coverage via brittle mocks is not safety
- When adding tests, ask: "What behavioral contract does this test encode? Will this contract still matter if I refactor the internals?"
- Surface test strategy decisions to the human: test level (unit vs. integration vs. e2e), mock boundaries, and what behavioral contracts the tests will encode

### AI-Generated Tests Require Human Judgment

AI tools write tests that match the code they just wrote. By construction, those tests pass. But passing is not the same as encoding a meaningful commitment. AI-generated tests tend toward implementation-coupled unit tests because the AI has full visibility into internal structure.

**Guidance**:
- Treat AI-generated test suites as a starting point for human review, not a finished artifact
- During code review, evaluate tests for contract quality: do they test behavior or implementation?
- When the AI proposes tests, it should state what behavioral contract each test encodes
- Flag tests that will break on refactoring without any behavior change — these are implementation contracts with short lifespans

---

## Context Detection

### Interactive Mode (Default — Recommended)
When user is working conversationally, implementing features, or iterating on code.

**Behavior**: Collaborate on implementation. Surface design decisions, test strategy choices, and architectural trade-offs for human input. This is the recommended mode for most work because it keeps humans in the convergence loop — catching design divergence early costs less than reviewing bulk changes after the fact.

### Ralph Loop Mode (Bounded Autonomous Workflow)
Triggered when:
- Running via `ralph-loop.sh` or similar orchestration
- Prompt references "implement spec" or completion signals
- Working through a `specs/` folder systematically

**Behavior**: Focus on implementation. Output `<promise>DONE</promise>` only when all acceptance criteria pass.

**When Loop Mode works well**: Mechanical tasks with low design ambiguity — formatting fixes, applying a well-defined pattern across files, implementing a spec where all design decisions are pre-made in the spec itself.

**When Loop Mode works poorly**: Features with design decisions embedded in implementation details. Specs capture intent but not every structural choice. When the AI makes those choices autonomously and threads them through many files, the human faces a bulk review that is harder to form a convergence opinion about than incremental course corrections would have been. Prefer Interactive Mode for anything with meaningful design latitude.

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
- **Test strategy checkpoint** (Interactive Mode): Before writing tests, surface the test approach to the human — what level (unit/integration/e2e), what behavioral contracts will be encoded, and where mock boundaries should be. This prevents investing in tests the human would reject on review

### Phase 3: Validate
- Confirm all existing tests pass
- Verify new functionality meets acceptance criteria
- Run the full test suite
- **Review test contract quality**: Do the new tests encode behavioral contracts (what the system does) or implementation contracts (how it does it internally)? Flag any tests that would break on refactoring without behavior change

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

**Reversibility check** - Verify changes can be safely rolled back.

Every change must have an answer to: "How do we undo this in minutes?"

If a release-safety policy module is active (e.g., `release-safety/full.md`), follow its detailed checklists. Otherwise, apply this generic checklist:

- [ ] Rollback approach identified (revert commit, disable flag, flip alias, etc.)
- [ ] Changes are additive where possible (no breaking removals in same release)
- [ ] Rollback plan documented in commit or PR description

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
- Audit trail exists for tracking
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
- Status: PASSED / FAILED

### Phase 4: Code Quality
- Dead code: None found / <issues>
- Duplication: None found / <issues>
- Encapsulation: Well-structured / <issues>
- Refactorings: <list any refactorings made>
- Status: PASSED / FAILED

### Phase 5: Security Review
- Dependencies: <tool> - X vulnerabilities (Critical: Y, High: Z)
- OWASP Top 10: <summary of findings>
- Anti-patterns: <summary>
- Fixes applied: <list>
- Status: PASSED / FAILED

### Phase 5.5: Release Safety
- Change type: Code-only / Schema / API / Infrastructure
- Rollback plan: <describe how to undo in minutes>
- Status: PASSED / FAILED / SKIPPED (docs/tests only)

### Overall
- All gates passed: YES/NO
- Notes: <any additional context>
```

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

| Avoid | Use Instead |
|-------|-------------|
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

**Special cases**:
- **System tools** (apt, pacman): Always ask - these require sudo and modify system state
- **Python packages**: Ask which method (pip, pipx, conda) and where (system, venv)
- **Development tools**: Consider if they should be in requirements.txt instead

---

## Policy Module System

Project-specific coding standards, git workflows, release safety practices, and external tool integrations are defined in policy modules located at `~/.claude/policies/`.

### How It Works

1. The global `~/.claude/CLAUDE.md` (this file) provides the core methodology
2. Each project's `.claude/CLAUDE.md` lists which policies to activate under `## Selected Policies`
3. At session start, read the listed policy files and apply them alongside the core methodology
4. If a project has no config or no `## Selected Policies` section, only the core methodology applies — inform the user once and suggest running `/ralph-setup`

### Available Policies

| Category | Policies | Purpose |
|----------|----------|---------|
| Languages | `languages/python.md`, `languages/go.md`, `languages/bash.md` | Coding standards |
| Git | `git/standard.md`, `git/platform-backend.md`, `git/simple.md` | Git workflows |
| Release Safety | `release-safety/full.md`, `release-safety/simplified.md`, `release-safety/minimal.md` | Rollback practices |
| Integrations | `integrations/jira-mcp.md`, `integrations/gitlab-glab.md` | External tools |

### Reading Policies

When you encounter a `## Selected Policies` section in a project's `.claude/CLAUDE.md`, read each listed file from `~/.claude/policies/` and apply its guidance for the remainder of the session. If a listed file does not exist, inform the user that the policy module is missing and suggest running `./install.sh` from the claude-code-global project to update.

### Policy Composition

Some policies extend others:
- `git/platform-backend.md` **includes all rules from** `git/standard.md` — listing only `git/platform-backend.md` is sufficient
- All other policies are independent — list each one you need

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
- Validation report frequency (every commit -> milestones only)
- Code quality refactor pass (always -> skip for hotfixes)
- Test requirements (must pass -> WIP commits allowed)
- Communication standards (strict -> relaxed for docs)
- Tool installation policy (always ask -> auto-approve dev deps)
- Git standards (partial: connectivity checks can be disabled)
- Release safety (full checklist -> simplified -> minimal for prototypes)

#### Non-Relaxable Guidelines (Security)
These CANNOT be disabled, only extended with additional rules:
- **Security Review Pass**: OWASP Top 10 checks, CVE scanning
- **Secrets Detection**: No hardcoded credentials in source

When relaxing guidelines, document the justification in the project config.

---

## Quick Reference

| Trigger | Mode | Behavior |
|---------|------|----------|
| Conversation/implementation | Interactive (default) | Collaborate, surface decisions, iterate with human input |
| `/ralph` command | Loop | Bounded autonomous mode for low-ambiguity tasks |
| `ralph-loop.sh` | Loop | External orchestration with fresh context per iteration |
| Working through specs/ | Loop | Implement, test, signal completion |

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
