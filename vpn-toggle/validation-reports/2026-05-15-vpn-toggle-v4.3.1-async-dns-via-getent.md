## Validation Report: AsyncDNSLookupAssert via getent (v4.3.1)
**Date**: 2026-05-15 12:17
**Commit**: pre-commit
**Status**: PASSED (Phase 5 deferred to /ralph-security-review)

### Phase 3: Tests
- Test suite: `/usr/bin/python3 -m pytest tests/` (from `vpn-toggle/`)
- Results: 195 passing, 0 failing
- Coverage: not collected this run (no coverage plugin invoked); `test_async_asserts.py` exercises the new `AsyncDNSLookupAssert` paths with a `_FakeGetentProcess` fake covering success, multi-record selection, AAAA-only, prefix mismatch, and non-zero exit
- Real-world smoke: invoked `AsyncDNSLookupAssert` against `git.attackiq.com` and compared to `ping`. Both now resolve to a `100.x` corp IP; previously the async assert returned the corp IP while `ping` saw the public AWS IP — the bug this fix targets.
- Status: PASSED

### Phase 4: Code Quality
- Dead code: `QDnsLookup` import removed from `asserts.py`; no other orphans introduced
- Duplication: `_FakeGetentProcess` extracted into a single test helper, replacing three inline `QDnsLookup`-fake classes (one per affected test). Net code reduction in tests.
- Encapsulation: `AsyncDNSLookupAssert._on_finished` is ~50 lines, on the boundary of the project guideline but structurally mirrors `AsyncPingAssert._on_finished` (the existing pattern). No mixed responsibilities; the regex-based IPv4 filter is the only non-trivial parsing step and is delegated to a module-level compiled `_IPV4_LINE_RE`.
- Refactorings: none required beyond the bug fix itself.
- Status: PASSED

### Phase 5: Security Review (via /ralph-security-review)
- Verdict: PASS
- Quoted summary from /ralph-security-review:
  - **Phase A — Dependency CVE Scan**: pip-audit 2.10.0. 10 CVEs in `aiohttp 3.13.3` in the system Python env, all fixed in 3.13.4. **Not introduced or affected by this diff** — vpn-toggle has no `requirements.txt`/`pyproject.toml` of its own; its imports are `PyQt6` and `requests`, neither flagged. The aiohttp findings are pre-existing system-env housekeeping, unrelated to v4.3.1.
  - **Phase B — OWASP Top 10 (AI-assisted, best-effort — not compliance evidence)**: clean. `QProcess.start('getent', ['hosts', hostname])` uses argv (no shell), hostname is local-config-sourced, getent stdout is parsed via compiled regex (not deserialized), only hostname + resolved IP are logged.
  - **Phase C — Secrets & Credential Scan**: inline AI scan (no detect-secrets/trufflehog/git-secrets installed). 0 findings. Diff contains test hostnames, the `100.` prefix string, IPv4 fixtures, and one IPv6 fixture — no credentials, keys, tokens, or `.env` files.
- Status: PASSED

### Phase 5.5: Release Safety
- Change type: Code-only (runtime check mechanism in the VPN monitor)
- Rollback plan: `git revert` of the v4.3.1 commit restores the `QDnsLookup`-based assert and the v4.3.0 version string. No schema, no on-disk format, no API surface affected. Metrics file format (`*.jsonl`) and signal payloads are unchanged.
- Behavioral note: the fix tightens the DNS check, so configurations that previously passed via false-green (VPN DNS not registered with systemd-resolved) will now fail and trigger the monitor's bounce logic. That is the intended outcome — the previous behavior was masking the very class of misconfiguration the check exists to detect.
- Status: PASSED

### Overall
- All gates passed: YES (Phase 5 explicitly deferred per the v3.13.0 skill split; security review must run separately before commit)
- Notes:
  - The sync `DNSLookupAssert` (used by tests and ad-hoc callers) was already on the correct nsswitch path via `socket.gethostbyname` and was not modified.
  - The historical claim in the v4.3.0 changelog entry that `AsyncDNSLookupAssert` uses `QDnsLookup` was left intact as accurate history; the v4.3.1 entry documents the switch to `getent`/`QProcess`.
