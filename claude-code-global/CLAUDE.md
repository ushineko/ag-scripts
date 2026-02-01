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

### Phase 6: Record History & Validation Artifacts
- Document significant learnings and decisions
- Update `history/` folder if project uses one
- Keep notes for future context
- **Save validation results** as project artifacts for tracking quality over time

#### Validation Artifacts

After completing validation phases (3-5), save results to track quality trends:

**Location**: `validation-reports/` or `history/validation/` in the project root

**When to save**:
- After completing all quality gates (Phases 3-5)
- Before final commit (Phase 7)
- For significant milestones or releases

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
- Mark spec as complete
- Commit with descriptive messages
- Deploy if applicable

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
