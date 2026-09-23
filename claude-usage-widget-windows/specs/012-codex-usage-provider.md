# Spec 012: Codex usage provider

**Issue:** [#15](https://github.com/ushineko/ag-scripts/issues/15)

## Context

The cross-platform usage monitor only displays Claude usage. Codex exposes the
signed-in account's rate limits through the supported app-server JSON-RPC API,
including utilization, reset times, plan, credits, and Business individual
limits.

## Requirements

- Fetch Codex usage through `codex app-server`, without reading credentials or
  calling private HTTP endpoints.
- Normalize variable-duration Codex windows and preserve their real duration.
- Share cached Codex readings across monitor processes without colliding with
  Claude account caches.
- Show Codex in terminal line and TUI modes alongside Claude.
- Keep failures isolated so either provider can continue displaying readings.
- Never label opaque individual-limit units as currency.

## Acceptance Criteria

- A signed-in Codex Business account shows its main allowance as a utilization
  bar with the correct duration and reset countdown.
- An available individual limit appears as a secondary percent-used value.
- JSON-RPC notifications and unrelated responses do not displace the matching
  `account/rateLimits/read` response.
- A missing CLI, signed-out account, timeout, or malformed response produces a
  compact provider-specific error while Claude remains visible.
- Claude and Codex cache files and locks are distinct.
- Unit tests cover normalization, response matching, rendering, and cache
  isolation; a real local app-server smoke test succeeds.

## Risks

- App-server payload fields can grow over time; normalization must tolerate
  missing optional fields and ignore unknown fields.
- Starting an app-server for each uncached poll is heavier than an HTTP request;
  the cooperative cache limits this to one process per freshness window.

## Alternatives Considered

- Reading `~/.codex/auth.json` and calling an internal endpoint was rejected
  because it couples the monitor to credentials and an unsupported protocol.
- Treating the primary window as always weekly was rejected because its
  duration is account-dependent.

## Technical Notes

Use the stable `account/rateLimits/read` request after the standard
`initialize`/`initialized` handshake. Select the `codex` limit bucket when it
is present, otherwise use the aggregate `rateLimits` object.

## Executive Summary

Add Codex as a second usage provider with the same compact bar-and-reset
experience as Claude while retaining the actual Codex window semantics.

## Status

Complete. Implementation, tests, live integration, and security review are
complete.
