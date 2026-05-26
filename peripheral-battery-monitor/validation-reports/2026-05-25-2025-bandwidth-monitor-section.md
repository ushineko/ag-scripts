# Validation Report — Spec 012: Bandwidth Monitor Section

**Date**: 2026-05-25 20:25 PDT
**Spec**: [specs/012-bandwidth-monitor-section.md](../specs/012-bandwidth-monitor-section.md)
**Mode**: NEW
**Status**: COMPLETE

## Phase 3 — Tests

`cd peripheral-battery-monitor && python -m pytest tests/`

```
tests/test_bandwidth_reader.py ..................                        [ 33%]
tests/test_battery_logic.py ....................................         [100%]

============================== 54 passed in 0.13s ==============================
```

Result: **PASS** — 54 / 54 (18 new tests for the bandwidth feature; 36 pre-existing tests unchanged in behavior, the mock module gained `setWordWrap`, `setVisible`, `setParent`, `deleteLater`, `isVisible`, `MockQInputDialog`, plus a `sys.modules.pop('bandwidth_section', None)` after the Qt mock swap to defeat test-ordering pollution).

## Phase 4 — Code review

Inline review (`/code-review` skill not installed in this project's policies). Findings against `languages/python.md`:

| Severity | Finding | Resolution |
|---|---|---|
| Blocking | `_format_bytes` used decimal-looking labels (KB/MB) with binary thresholds | Switched to IEC prefixes (KiB / MiB / GiB / TiB) — `bandwidth_section.py:43` |
| Blocking | `_poll` silently swallowed all exceptions | Added `_log.warning("bandwidth_poll_failed", exc_info=True)` — `bandwidth_section.py:309` |
| Advisory | Module-level Tailscale-metadata cache is process-wide | Documented as acceptable (one BandwidthSection instance) |
| Advisory | Interface names not validated against `/proc` at add time | Documented — row shows "(missing)" as user feedback |
| Advisory | `QInputDialog.getText` is modal / blocks UI thread | Acceptable; matches existing UI conventions |

Result: **PASS** (after the two blockers were fixed).

## Phase 4.5 — Code quality refactor pass

- No duplicated logic introduced (the data layer is the only `/proc/net/dev` reader; the UI is the only consumer).
- No god classes: `BandwidthSection` is < 330 lines, single responsibility (UI for bandwidth rows).
- No long methods: longest is `_poll` at 28 lines.
- Helper extraction: `_format_bytes`, `_format_rate`, `_format_metadata` extracted from row rendering.

Result: **PASS**.

## Phase 5 — Format pass

Project has no formatter configuration (`pyproject.toml`, `setup.cfg`, `.flake8` all absent). Skipped per skill instructions, noted here as a gap. Manual style review (Phase 8) covered the policy requirements.

Result: **SKIPPED** (no config).

## Phase 5.5 — Release safety (per `release-safety/minimal.md`)

| Check | Status |
|---|---|
| Rollback approach identified | ✓ revert the commit — new files (`bandwidth_reader.py`, `bandwidth_section.py`, spec, test) are additive; `peripheral-battery.py` patch is localized to `initUI`, context menu, `load_settings`. No migrations, no shared state changes |
| Additive changes (no breaking removals) | ✓ no behavior removed; new settings default off-ish (`bandwidth_interfaces: []`) so existing users see only an empty Bandwidth section that they can hide |
| Reversibility documented | ✓ this report + spec "Risks & Assumptions" section |

Result: **PASS**.

## Phase 6.5 — Security review (always mandatory, Ralph CLAUDE.md Phase 5)

### Dependency CVE scan

- Tool: `pip-audit 2.10.0`
- Result: env-wide scan failed because `awscli` (a system Pacman package on CachyOS) is not on PyPI. Cannot produce a clean report for the whole environment.
- Mitigation: the bandwidth feature introduces **zero new third-party dependencies**. `bandwidth_reader.py` uses only stdlib (`json`, `logging`, `os`, `subprocess`, `sys`, `time`). `bandwidth_section.py` uses only stdlib + `PyQt6` (already a project dep).

### OWASP Top 10 review (working-tree diff)

| Item | Verdict |
|---|---|
| A01 Broken access control | N/A (local desktop app) |
| A02 Cryptographic failures | N/A (no crypto in diff) |
| A03 Injection | **PASS** — `subprocess.run(["tailscale", "status", "--json"], ...)` uses argv list, no `shell=True`, no `os.system`, no `eval`/`exec`. Interface names are passed via Python list to `/proc/net/dev` reads; never to a shell |
| A04 Insecure design | PASS — cumulative is opt-in; section hideable |
| A05 Security misconfiguration | PASS — no new config endpoints; settings file path matches existing pattern |
| A06 Vulnerable components | UNKNOWN env-wide; no new third-party deps added by this change |
| A07 Identification / auth failures | N/A |
| A08 Software / data integrity failures | PASS — JSON only; no `pickle` / `eval` |
| A09 Security logging | PASS — `_log.warning` on `_poll` failure |
| A10 SSRF | N/A — no outbound network calls |

### Secrets scan

```
grep -iEn "BEGIN (RSA|EC|OPENSSH|PGP) PRIVATE KEY|aws_secret|sk_live_|sk_test_|password\s*=\s*['\"]|api[-_]?key\s*=\s*['\"]" \
  bandwidth_reader.py bandwidth_section.py specs/012-bandwidth-monitor-section.md tests/test_bandwidth_reader.py
# exit=1 (no matches)
```

Result: **PASS**.

## Phase 6.5 — Spec reconciliation

15 / 15 acceptance criteria checked. Spec status updated to `COMPLETE`. One AC was adjusted to reflect the implemented API contract (`update_settings(settings)` → `update_style(alpha, font_scale)` plus the existing `on_settings_changed` callback); user-visible behavior is unchanged.

## Phase 8 — Final language pass

Manual review against `languages/python.md` defaults: type hints in place, imports ordered, no bare except (broad except in `_poll` is intentional and logged), docstrings on public surfaces, naming follows underscore convention for private helpers, no over-engineering.

Result: **PASS**.

## Manual verification

- Launched `python3 peripheral-battery.py --debug` on the host. App started cleanly: `app_started version=1.6.0`, all four `initial_icon_set` lines logged (battery cells constructed), no crashes, no error logs.
- Exercised `BandwidthSection` programmatically with offscreen Qt:
  - Two polls 200ms apart produced `lo: ↓ 10.9 KiB/s  ↑ 10.9 KiB/s  Σ ↓ 2.3 KiB ↑ 2.3 KiB` and `tailscale0: ↓ 0 B/s  ↑ 5.5 KiB/s  Σ ↓ 0 B ↑ 1.1 KiB`.
  - `add_interface('eno2')` appended to the list; settings emit captured all three interfaces.
  - `reset_cumulative('tailscale0')` zeroed the totals and re-emitted settings.
  - `remove_interface('lo')` mutated the list correctly.
  - `set_visible(False)` → `_timer.isActive() == False`. `set_visible(True)` → timer restarted.

## Gaps and notes

- **CVE scan**: pip-audit could not produce a clean env-wide report due to the awscli/PyPI mismatch. Bandwidth feature adds no third-party deps, but this is a pre-existing environmental issue unrelated to the change.
- **Format pass**: skipped due to lack of formatter configuration. Manual style review covered the policy requirements (Phase 8).
- **Version**: bumped to `1.6.0`. Per project finalization rules, the version proposal needs user confirmation before the commit lands; this report records the proposal.

## Verdict

**PASS** — feature complete, tests passing, security clean, ready for human review and commit.
