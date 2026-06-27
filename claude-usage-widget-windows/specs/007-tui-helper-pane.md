# Spec 007: Terminal (TUI) modes for helper panes

> **Note**: This work has no associated issue tracker ticket (personal public repo, per project policy).

## Status: COMPLETE

## Problem

The widget only renders through PySide6 (floating window + tray). There is no
way to display Claude usage in a terminal multiplexer pane (tmux, herd, etc.),
which is where a lot of work already happens. The existing `--no-gui` prints a
multi-line one-shot report and exits — too tall and verbose for a small status
pane, and not self-updating.

We want a terminal display that is Qt-free (so it runs in a minimal/headless
pane without PySide6) and compact enough for a 1-line helper pane.

## Decision

Add two terminal modes, both reusing the existing Qt-free data layer
(`oauth.fetch_claude_usage()`, `display.py`) — no PySide6 import on these paths:

1. `--tui` — a long-running, self-refreshing display that owns the pane and
   redraws a single compact line in place on the poll interval. Ctrl-C exits.
2. `--line` — prints one compact status line and exits. Intended to be called
   repeatedly by a tmux `status-interval` / `watch` / herd status command.

Both render through one shared builder (`build_line`) so the two modes stay
visually consistent. Rendering uses **`rich`** rather than hand-rolled escape
codes: `build_line` returns a styled `rich.text.Text`, and a `rich.console.Console`
decides whether to emit color (TTY / NO_COLOR / `--no-color`). The live mode uses
`rich.live.Live` for the in-place redraw, plus last-known-good/stale handling and
rate-limit backoff.

Rationale for a single adaptive line (not a multi-row box): the user wants the
live render to be as compact as possible — ideally 1 line. Rationale for `rich`
over hand-rolled sequences (user request): the library handles color detection,
width, and screen clearing/restore (via Live's alternate screen) portably,
removing all literal `\x1b[...]` codes from the project.

## Implementation

- `src/tui.py` (new, Qt-free; depends on `rich`) —
  - `build_line(data, *, width=None, bar=False, note=None) -> rich.text.Text`:
    builds the compact line. Segments, highest priority first: `Claude` label,
    5h (with optional bar), 7d, reset countdown, optional Opus/Sonnet 7d
    breakdown, stale note. Lower-priority segments are dropped to fit `width`
    (then the core is truncated as a last resort). Color is carried as rich
    styles via `_usage_style` (same thresholds as `display.usage_color`).
    Handles the error / not-logged-in / stale cases with a short status line.
  - `build_tui_view(data, *, note=None)`: the full-width `--tui` renderable — a
    `Table.grid(expand=True)` with a `rich.progress_bar.ProgressBar` (5h, colored
    by `_usage_style`) that stretches to fill, the stats (`_stat_segments`)
    trailing it, and the reset countdown floated to the far right (slack split
    bar:spacer = 3:1). Falls back to the compact `build_line` `Text` for the
    not-logged-in / error states.
  - `run_line(color) -> int`: one fetch, `Console.print(build_line(...), soft_wrap=True)`, exit.
  - `run_tui(interval, color) -> int`: `with Live(console, screen=True)` → fetch →
    `live.update(build_tui_view(...), refresh=True)` → sleep loop; keeps
    last-known-good on transient errors and marks it stale; backs off the
    interval on `rate_limited` (honoring `retry_after`, capped); Ctrl-C exits
    cleanly (Live restores the pane; return 0).
- `requirements.txt` — add `rich>=13.0.0`.
- `src/main.py` — add `--tui`, `--line`, `--interval N`, `--no-color` args.
  Keep logging **off the terminal** in `--tui`/`--line` modes (the display owns
  the pane; stderr would interleave with the redrawn line) — logs are discarded
  unless `--log-file` is given, via `setup_logging(console=False)`. Dispatch in
  `main()` before the GUI path. Color auto-enables only when stdout is a TTY and
  `NO_COLOR` is unset (so `--line` piped into a status bar emits plain text by
  default); `--no-color` forces it off.
- `src/logging_config.py` — `setup_logging(..., console=False)` routes logs to
  `log_file` if given, otherwise discards them (no terminal handler).

## Acceptance Criteria

- [x] `--line` fetches once, prints a single compact line to stdout, and exits 0; logs are kept off the terminal (verified: `--line --no-color` emits only the line on stdout, 0 bytes on stderr, even with `--debug`; `setup_logging(console=False)`)
- [x] `--tui`/`--line` never interleave log lines with the display: logs are discarded unless `--log-file` is given, where they are captured to the file with nothing on the terminal (`test_logging_config.py`)
- [x] `--tui` runs a self-refreshing full-width dashboard via `rich.live.Live` (alternate screen — pane cleared on entry, restored on exit): a 5h progress bar that stretches to fill, stats trailing it, reset floated right; exits cleanly (return 0) on Ctrl-C (`tui.run_tui`/`build_tui_view`; `TestBuildTuiView`, `TestRunTuiBackoff`)
- [x] Neither `--tui` nor `--line` imports PySide6 (verified: `'PySide6' in sys.modules` is False after running both paths; `tui.py` imports only `rich`/`oauth`/`display`, `main` mode wrappers import `tui`/`config`)
- [x] `--line` is width-aware: lower-priority segments (model → reset → 7d) are dropped so the 5h reading always shows; the core is truncated as a last resort (`build_line` drop loop + `Text.truncate`; `TestWidthTruncation`). `--tui` fills the pane width via `Table.grid(expand=True)` + an expanding `ProgressBar` (`TestBuildTuiView.test_bar_stretches_to_fill_width`)
- [x] 5h utilization, 7d utilization, reset countdown, and Opus/Sonnet 7d breakdown (when present and non-zero) are rendered, matching the GUI widget's data (`build_line`; `_model_segment` mirrors `widget._render_usage`)
- [x] Color: carried as rich styles (`_usage_style`, same thresholds as `display.usage_color`); the `Console` emits it only on a TTY with `NO_COLOR` unset, and `--no-color` forces it off (`main._use_color` → `Console(no_color=...)`; `TestColorEmission`/`test_color_thresholds_as_styles`)
- [x] Error / not-logged-in states render a short readable status (no traceback); `--tui` preserves the last good reading and marks it stale on transient errors (`build_line` status branch; `run_tui` last_good/note; `TestErrorStates`)
- [x] `--tui` backs off its poll interval on HTTP 429 (rate_limited), honoring `retry_after`, and returns to the base interval on the next success (`run_tui` backoff; `TestRunTuiBackoff`)
- [x] `--interval N` overrides the base poll interval for `--tui` (minimum enforced via `max(MIN_INTERVAL, interval)`); default comes from config `update_interval_seconds` (`main.run_tui_mode`)
- [x] Tests cover `build_line` (normal, error, None, stale, width truncation, color styles + emission, model breakdown), `build_tui_view` (bar/stats/reset render, width-fill, stale note, error fallback), and the `run_tui` loop; full suite passes (106 passing)
- [x] README updated (Usage, CLI Options table, Changelog) and version bumped (3.0.2 → 3.1.0)
- [x] Validation report created in `validation-reports/`
