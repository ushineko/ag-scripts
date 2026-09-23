# Validation Report — v1.21.0 Codex Usage Provider

**Date**: 2026-09-22
**Spec**: `specs/040-codex-usage-provider.md`
**Issue**: [#15](https://github.com/ushineko/ag-scripts/issues/15)
**Version**: 1.20.0 → 1.21.0 (approved by the user)

## Result

The monitor now has a separately toggleable Codex section with a main
allowance bar, server-reported duration, reset countdown, and Business
individual-limit usage. It consumes the same Codex cache as every standalone
terminal viewer, limiting all active monitors to one upstream read per cache
window.

## Tests

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /usr/bin/python3 -m pytest -q
276 passed, 36 subtests passed in 2.97s
```

Focused tests cover duration labels, color thresholds, and reset formatting.
The mirrored `codex_usage.py` and `usage_cache.py` files are byte-identical to
the standalone monitor copies. `compileall` and `git diff --check` pass.

## Live integration

The shared provider was verified against the signed-in local Codex app-server.
The current Business response included both the weekly allowance and its
individual limit; no account identifier entered the normalized result.

## Security review

Verdict: **CONCERNS** because the installed `pip-audit 2.10.0` cannot run: its
environment is missing the `filelock` dependency. No dependency files changed.

The AI-assisted OWASP review found no injection, auth, access-control,
deserialization, XSS, SSRF, or sensitive-data exposure issue. The app-server
command is fixed, normalized fields are rendered as text, cache path components
are sanitized, and scans found no credential literals. No dependency manifest
or agent configuration changed.

## Release safety

The section is additive and independently toggleable. A disabled section does
not poll Codex. Existing settings merge with the new enabled-by-default key.
Rollback is a normal commit revert with no migration or external state to undo.
