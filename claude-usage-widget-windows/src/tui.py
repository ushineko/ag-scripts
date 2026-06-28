"""Terminal (TUI) rendering of Claude usage for helper panes.

Qt-free by design so it runs in a minimal/headless terminal pane (tmux, herd,
etc.) without PySide6. Rendering is done with `rich` rather than hand-rolled
escape codes: `rich.console.Console` handles color detection (TTY / NO_COLOR)
and width, and `rich.live.Live` (alternate screen) handles the in-place redraw,
clearing the launching shell's echo on entry and restoring the pane on exit.

Reuses the same data layer as the GUI: ``oauth.fetch_claude_usage()`` and
``display.format_percentage``.

Two modes:
  * ``run_line``  — fetch once, print one compact line, exit (for status bars).
  * ``run_tui``   — long-running, self-refreshing single line via Live.
"""

from __future__ import annotations

import signal
import time

import structlog
from rich.console import Console
from rich.live import Live
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

from .display import format_percentage
from .oauth import fetch_claude_usage, get_time_until_reset
from .usage_cache import fetch_usage_cached

log = structlog.get_logger(__name__)

# Segment separator and live-loop tuning.
SEP = " · "
MIN_INTERVAL = 5          # floor for --interval (seconds)

# Compact, single-line error/status text (the full GUI messages are too long).
_ERR_TEXT = {
    "auth_expired": "auth expired",
    "auth_backoff": "auth retry",
    "rate_limited": "rate limited",
    "api_error": "API error",
    "offline": "offline",
    "invalid_response": "bad response",
}


def _err_text(error_code: str | None) -> str:
    if not error_code:
        return "no data"
    return _ERR_TEXT.get(error_code, error_code)


def _fmt_age(seconds: float) -> str:
    """Human-readable duration, e.g. '3m ago'."""
    minutes = int(seconds // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes}m ago"
    return f"{minutes // 60}h{minutes % 60}m ago"


def _staleness_note(data, fetched_at: float | None, interval: int) -> str | None:
    """A 'cached Xm ago' note when a good reading is older than ~1.5x interval.

    The age comes from the shared cache's ``fetched_at`` (wall clock), so every
    pane shows a consistent staleness regardless of when it started.
    """
    if not isinstance(data, dict) or "five_hour" not in data or fetched_at is None:
        return None
    age = time.time() - fetched_at
    if age > interval * 1.5:
        return f"cached {_fmt_age(age)}"
    return None


def _usage_style(util: float | None) -> str:
    """Rich style name for a utilization percentage, matching the GUI thresholds
    (>80 red, 50-80 yellow, below 50 green, unknown dim)."""
    if util is None:
        return "dim"
    if util > 80:
        return "red"
    if util >= 50:
        return "yellow"
    return "green"


def _seg_five_hour(util: float | None) -> Text:
    """The core 5-hour segment (never dropped): 'Claude 5h XX%'."""
    style = _usage_style(util)
    t = Text("Claude 5h ")
    t.append(format_percentage(util), style=style)
    return t


def _assemble(core: Text, opt: list[tuple[str, Text]], present: list[str]) -> Text:
    """Join the core segment with the surviving optional segments using SEP."""
    out = core.copy()
    for name, seg in opt:
        if name in present:
            out.append(SEP, style="dim")
            out.append_text(seg)
    return out


def build_line(
    data: dict | None,
    *,
    width: int | None = None,
    note: str | None = None,
) -> Text:
    """Build a single compact status line as a styled rich ``Text`` (the --line
    mode, and the --tui fallback for error states).

    Segments, in display order: ``Claude 5h`` · 7d · reset · model breakdown ·
    note. When ``width`` is given, lower-priority segments are dropped
    (note → model → reset → 7d) so the 5h reading always fits; if the core alone
    still overflows it is truncated. ``data`` may be ``None`` (not logged in) or
    an error dict (no ``five_hour``), which render as a short status line. Color
    is carried as styles; the ``Console`` decides whether to emit it.
    """
    # No usable reading -> short status line.
    if not isinstance(data, dict) or "five_hour" not in data:
        text = "not logged in" if data is None else _err_text((data or {}).get("error"))
        line = Text(f"Claude — {text}", style="dim", no_wrap=True, overflow="crop")
        if width:
            line.truncate(width)
        return line

    five = data.get("five_hour", {})
    seven = data.get("seven_day", {})
    util5 = five.get("utilization")
    util7 = seven.get("utilization")
    resets_at = five.get("resets_at", "")

    core = _seg_five_hour(util5)

    # Optional segments tagged for width-driven dropping.
    seg7 = Text("7d ")
    seg7.append(format_percentage(util7), style=_usage_style(util7))
    opt: list[tuple[str, Text]] = [("7d", seg7)]

    if resets_at:
        opt.append(("reset", Text(f"reset {get_time_until_reset(resets_at)}")))

    model = _model_segment(data)
    if model:
        opt.append(("model", Text(model, style="dim")))

    if note:
        opt.append(("note", Text(f"({note})", style="dim")))

    present = [name for name, _ in opt]
    drop_order = ["note", "model", "reset", "7d"]

    line = _assemble(core, opt, present)
    while width and line.cell_len > width and present:
        for name in drop_order:
            if name in present:
                present.remove(name)
                break
        line = _assemble(core, opt, present)

    # Core alone may still exceed an ultra-narrow pane; truncate as a last resort.
    if width and line.cell_len > width:
        line.truncate(width)
    line.no_wrap = True
    line.overflow = "crop"
    return line


def _model_segment(data: dict) -> str:
    """7-day per-model breakdown, e.g. 'opus 12% sonnet 19%' (empty if none)."""
    parts = []
    for key in ("seven_day_opus", "seven_day_sonnet"):
        bucket = data.get(key)
        if bucket and bucket.get("utilization", 0) > 0:
            name = key.replace("seven_day_", "")
            parts.append(f"{name} {bucket['utilization']:.0f}%")
    return " ".join(parts)


def _stat_segments(data: dict) -> Text:
    """The trailing stats for the --tui line: 5h% · 7d 7d% · model breakdown."""
    util5 = data.get("five_hour", {}).get("utilization")
    util7 = data.get("seven_day", {}).get("utilization")
    t = Text(" ")
    t.append(format_percentage(util5), style=_usage_style(util5))
    t.append("  ·  7d ", style="dim")
    t.append(format_percentage(util7), style=_usage_style(util7))
    model = _model_segment(data)
    if model:
        t.append("  ·  ", style="dim")
        t.append(model, style="dim")
    return t


def build_tui_view(data: dict | None, *, note: str | None = None):
    """Build the full-width --tui renderable: a 5h progress bar that stretches to
    fill the pane, the stats trailing it, and the reset countdown right-aligned.

    Returns a `rich` renderable (a `Table.grid`), or the compact `build_line`
    `Text` for the not-logged-in / error states (no `five_hour` to chart).
    """
    if not isinstance(data, dict) or "five_hour" not in data:
        return build_line(data, note=note)

    five = data["five_hour"]
    util5 = five.get("utilization")
    resets_at = five.get("resets_at", "")
    style = _usage_style(util5)

    # Slack is split between the bar (3) and a spacer before the reset (1): the
    # bar stretches to use most of the width, while the reset floats to the far
    # right with a clean gap. Fixed columns size to their content.
    grid = Table.grid(expand=True, padding=0)
    grid.add_column(no_wrap=True)                        # "Claude  5h "
    grid.add_column(ratio=3)                             # the bar (stretches)
    grid.add_column(no_wrap=True)                        # stats
    grid.add_column(ratio=1)                             # spacer / gap
    grid.add_column(no_wrap=True, justify="right")       # reset / stale note

    bar = ProgressBar(
        total=100,
        completed=min(100, max(0, util5 or 0)),
        width=None,                                       # fill the ratio column
        complete_style=style,
        finished_style=style,
        style="grey30",                                   # unfilled track
        pulse=False,
    )

    if note:
        right = Text(f" ({note})", style="dim")
    elif resets_at:
        right = Text(f" resets {get_time_until_reset(resets_at)}", style="dim")
    else:
        right = Text("")

    grid.add_row(Text("Claude  5h "), bar, _stat_segments(data), Text(""), right)
    return grid


def run_line(color: bool, *, use_cache: bool = True, ttl: int = 60) -> int:
    """Fetch usage once, print a single compact line, and exit.

    By default reads through the cooperative cache (``ttl`` freshness window) so
    repeated/concurrent callers don't each hit the API; ``use_cache=False`` does
    a direct per-process fetch.
    """
    log.info("starting_line_mode", cache=use_cache)
    console = Console(no_color=not color, highlight=False)
    if use_cache:
        data, _ = fetch_usage_cached(ttl)
    else:
        data = fetch_claude_usage()
    # soft_wrap keeps the line intact (no wrapping/cropping) for status bars.
    console.print(build_line(data), soft_wrap=True)
    return 0


def run_tui(interval: int, color: bool, *, use_cache: bool = True) -> int:
    """Run a self-refreshing full-width dashboard until interrupted.

    Uses ``rich.live.Live`` on the alternate screen, so the launching shell's
    echo is cleared on entry and the pane is restored on exit. By default reads
    through the cooperative cache so multiple panes share ~1 API fetch per
    interval — the shared gate (honoring ``Retry-After``) handles throttling, so
    no per-process backoff is needed here. ``use_cache=False`` fetches directly.
    Ctrl-C exits.
    """
    base = max(MIN_INTERVAL, interval)
    console = Console(no_color=not color, highlight=False)
    log.info("starting_tui_mode", interval=base, cache=use_cache)
    try:
        with Live(console=console, screen=True, auto_refresh=False) as live:
            # Repaint immediately on a terminal/pane resize. With auto_refresh
            # off, Live only redraws on update(), so without this the pane goes
            # blank after a resize until the next poll (`base` seconds away).
            # Live uses an RLock, so refreshing from the main-thread signal
            # handler is reentrant-safe; time.sleep is auto-resumed after the
            # handler (PEP 475), so the poll cadence is unchanged. SIGWINCH is
            # Unix-only — the Windows/GUI paths never reach here.
            prev_winch = None
            if hasattr(signal, "SIGWINCH"):
                def _on_resize(_signum, _frame):
                    try:
                        live.refresh()
                    except Exception:  # a redraw hiccup must not kill the handler
                        log.debug("resize_refresh_failed", exc_info=True)
                prev_winch = signal.signal(signal.SIGWINCH, _on_resize)
            try:
                while True:
                    if use_cache:
                        data, fetched_at = fetch_usage_cached(base)
                    else:
                        data, fetched_at = fetch_claude_usage(), time.time()
                    note = _staleness_note(data, fetched_at, base)
                    live.update(build_tui_view(data, note=note), refresh=True)
                    time.sleep(base)
            finally:
                if prev_winch is not None:
                    signal.signal(signal.SIGWINCH, prev_winch)
    except KeyboardInterrupt:
        log.info("tui_exit")
        return 0
