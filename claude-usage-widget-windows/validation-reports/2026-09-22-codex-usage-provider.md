# Validation Report — v3.5.0 Codex Usage Provider

**Date**: 2026-09-22
**Spec**: `specs/012-codex-usage-provider.md`
**Issue**: [#15](https://github.com/ushineko/ag-scripts/issues/15)
**Version**: 3.4.0 → 3.5.0 (approved by the user)

## Result

The terminal monitor now displays Codex beside Claude using the supported
app-server protocol. It preserves server-reported window durations, reset
times, Business individual-limit values, and percent used. All viewers share a
provider-specific cache gate and lock with the peripheral monitor.

## Tests

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /usr/bin/python3 -m pytest -q
205 passed in 0.23s
```

Coverage added for JSON-RPC response matching amid notifications, Business
payload normalization, aggregate-bucket fallback, dynamic rendering, and cache
namespace isolation. `compileall` and `git diff --check` pass.

## Live integration

A real `codex app-server` handshake and `account/rateLimits/read` completed in
0.76 seconds. The response normalized to a 10,080-minute primary window and a
Business individual limit. A second caller reused the same cached value and
timestamp without launching another app-server.

## Security review

Verdict: **CONCERNS** because the installed `pip-audit 2.10.0` cannot run: its
environment is missing the `filelock` dependency. No dependency files changed.

The AI-assisted OWASP review found no injection, auth, access-control,
deserialization, XSS, SSRF, or sensitive-data exposure issue. The subprocess
uses a fixed command and JSON-RPC methods; cache path components are sanitized.
Normalization explicitly omits the app-server account ID, credentials are
never read, and scans found no credential literals. No dependency manifest or
agent configuration changed.

## Release safety

The change is additive. Existing Claude cache filenames and call signatures
remain valid. Rollback is a normal commit revert; cached Codex JSON contains no
credentials and can be left in place or deleted safely.
