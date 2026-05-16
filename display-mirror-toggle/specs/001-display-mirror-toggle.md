# Spec 001: Display Mirror Toggle

## Overview

A small bash utility to toggle a KDE Plasma 6 / Wayland display mirror relationship between two outputs on or off, while disabling/enabling the source output in the same atomic kscreen-doctor call. Designed to be hotkey-bindable and primarily intended for the FUERAN-dummy / Philips-OLED workaround (see `~/git/sysadmin/docs/sunshine-moonlight-setup.md`), but parameterized so it works for any source/replica pair.

## Problem Statement

- Toggling a kscreen mirror from the CLI is awkward: the verb is `mirror` (not the displayed "replication source"), the source and the replica's mirror setting must change in one atomic call, and disabling a source without clearing the mirror first produces a `Position of enabled output ... is negative` error because KDE recomputes the replica's geometry from a now-disabled source.
- The working command pair was discovered during a multi-turn debugging session and is currently only documented in `~/git/sysadmin/docs/sunshine-moonlight-setup.md`. A utility script makes the toggle invocable from a hotkey, removes the chance of someone re-discovering the verb gotcha later, and centralizes the logic in one tested place.

## Requirements

### Functional Requirements

- [x] Toggle behavior: default invocation flips between "mirror active" and "mirror off + source disabled"
- [x] Explicit modes: `--enable` (force-enable + restore mirror), `--disable` (force-disable + clear mirror), `--status` (report state, no change)
- [x] Configurable source/replica via `--source CONNECTOR` and `--replica CONNECTOR` with defaults `HDMI-A-1` and `DP-3` (the user's current setup)
- [x] Idempotent: enabling an already-enabled mirror or disabling an already-disabled one is a no-op with informational output, not an error
- [x] Standard help (`-h`/`--help`) and version (`-v`/`--version`) flags
- [x] `-q`/`--quiet` for minimal output (suitable for keybind invocation)

### Non-Functional Requirements

- [x] Bash only — no Python, no extra runtime dependencies beyond `kscreen-doctor`
- [x] Detect missing `kscreen-doctor` and exit cleanly with a clear error
- [x] Use the atomic `kscreen-doctor` invocation pattern (one call sets both verbs) so KDE validates the final state, not intermediate states
- [x] Strip ANSI color codes when parsing `kscreen-doctor -o` so detection works regardless of terminal/non-terminal output
- [x] Exit codes: 0 success, 1 runtime error, 2 dependency missing
- [x] No sudo required

## Acceptance Criteria

- [x] `display-mirror-toggle --status` reports current source-enabled and replica-mirroring state without side effects
- [x] `display-mirror-toggle` (no args) toggles between mirror-active and mirror-off states
- [x] `display-mirror-toggle --disable` issues `kscreen-doctor output.<REPLICA>.mirror.none output.<SOURCE>.disable` atomically
- [x] `display-mirror-toggle --enable` issues `kscreen-doctor output.<SOURCE>.enable output.<REPLICA>.mirror.<SOURCE>` atomically
- [x] `--source` and `--replica` flags override defaults
- [x] Idempotent enable/disable: no error when state is already correct, output indicates "already `<state>`"
- [x] `--help` documents all flags and shows examples
- [x] `-v`/`--version` prints the script version
- [x] Missing `kscreen-doctor` exits with code 2 and an actionable error message
- [x] Tests cover argument parsing (help, version, invalid options, status flag) without requiring an active KDE session

## Technical Design

### Language

Bash. The toggle is a thin wrapper around two `kscreen-doctor` invocations and a parse of its `-o` output. No state to manage, no GUI, no logging concerns beyond stdout/stderr. Same pattern as `bluetooth-reset`.

### Commands Used

- `kscreen-doctor -o` — list current display state (parsed, ANSI-stripped)
- `kscreen-doctor output.<replica>.mirror.<source> output.<source>.enable` — restore mirror
- `kscreen-doctor output.<replica>.mirror.none output.<source>.disable` — clear mirror and disable source

### State Detection

Parse `kscreen-doctor -o` output. Strip ANSI escape sequences first (`sed 's/\x1b\[[0-9;]*m//g'`). Walk the per-output blocks by `^Output:` lines, recording for each connector: enabled flag, and any `replication source: <N>` value. The "mirror active" state is defined as (source enabled) AND (replica's replication source != 0).

### Output Format

```text
display-mirror-toggle v1.0.0
Source:  HDMI-A-1 (enabled)
Replica: DP-3 (mirroring HDMI-A-1)
State:   mirror active

Disabling mirror...
Done. State: mirror off.
```

## File Structure

```text
display-mirror-toggle/
├── README.md
├── display-mirror-toggle.sh
├── install.sh
├── uninstall.sh
├── specs/
│   └── 001-display-mirror-toggle.md
├── tests/
│   └── test_display_mirror_toggle.sh
└── validation-reports/
```

## Test Plan

Tests are bash-only and must not require an interactive KDE session. They cover:

- [x] Script is executable
- [x] `--help` includes "Usage:" and lists `--source`, `--replica`, `--enable`, `--disable`, `--status`
- [x] `--version` prints the version string
- [x] Invalid option exits non-zero
- [x] `--source` without a value exits non-zero
- [x] `--replica` without a value exits non-zero
- [x] Conflicting modes (`--enable --disable`) exit non-zero
- [x] When `kscreen-doctor` is absent (simulated by PATH stripping in a subshell), the script exits with code 2

State-mutation paths (`--enable`, `--disable`, no-arg toggle) are validated manually on the live system per the validation report. Automated tests do not invoke real `kscreen-doctor` calls.

## Status

**Status: COMPLETE**

---

## Notes

The verb is `mirror`, not `replicate` or `replication`, despite `kscreen-doctor -o` displaying the field as "replication source". This was discovered the hard way (a `replication.none` attempt parsed as junk integer); the script must hardcode `mirror`.

Disabling the source without clearing the replica's mirror first fails with `Position of enabled output <replica> is negative (-X, Y)` — KDE recomputes replica geometry from the disabled source. The script must always pair the verbs in one atomic call.
