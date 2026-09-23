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

import os
import signal
import time
from datetime import datetime, timezone

import structlog
from rich.console import Console, Group
from rich.live import Live
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

from .accounts import discover_or_default
from .codex_usage import fetch_codex_usage, is_codex_installed
from .display import format_percentage
from .oauth import fetch_claude_usage, get_time_until_reset
from .usage_cache import fetch_usage_cached
from .usage_shape import (
    SHAPE_CREDITS,
    SHAPE_UNAVAILABLE,
    credits_view,
    detect_shape,
    format_credits,
)

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
    "not_logged_in": "not logged in",
    "not_installed": "not installed",
    "timeout": "timed out",
    # The shared cache has no reading for this account yet (cold start, or a
    # gate still closed after a failure). Distinct from "not logged in": the
    # credentials are present and fine, there is simply nothing to show yet.
    "no_data": "no reading yet",
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
    if (not isinstance(data, dict)
            or ("five_hour" not in data and data.get("provider") != "codex")
            or fetched_at is None):
        return None
    age = time.time() - fetched_at
    if age > interval * 1.5:
        return f"cached {_fmt_age(age)}"
    return None


def _severity_style(severity: str | None) -> str:
    """Rich style for a ``spend.severity`` value, mirroring _usage_style's palette."""
    return {
        "normal": "green",
        "warning": "yellow",
        "elevated": "yellow",
        "critical": "red",
        "exceeded": "red",
    }.get(severity, "dim")


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


def _seg_five_hour(util: float | None, label: str = "Claude") -> Text:
    """The core 5-hour segment (never dropped): '<label> 5h XX%'."""
    style = _usage_style(util)
    t = Text(f"{label} 5h ")
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
    label: str = "Claude",
) -> Text:
    """Build a single compact status line as a styled rich ``Text`` (the --line
    mode, and the --tui fallback for error states).

    Segments, in display order: ``Claude 5h`` · 7d · reset · model breakdown ·
    note. ``label`` replaces the leading ``Claude`` so a multi-account render
    can identify which account the line belongs to. When ``width`` is given, lower-priority segments are dropped
    (note → model → reset → 7d) so the 5h reading always fits; if the core alone
    still overflows it is truncated. ``data`` may be ``None`` (not logged in) or
    an error dict (no ``five_hour``), which render as a short status line. Color
    is carried as styles; the ``Console`` decides whether to emit it.
    """
    if isinstance(data, dict) and data.get("provider") == "codex":
        return build_codex_line(data, width=width, note=note, label=label)

    # No usable reading -> short status line.
    if not isinstance(data, dict) or "five_hour" not in data:
        text = "not logged in" if data is None else _err_text((data or {}).get("error"))
        line = Text(f"{label} — {text}", style="dim", no_wrap=True, overflow="crop")
        if width:
            line.truncate(width)
        return line

    shape = detect_shape(data)

    if shape == SHAPE_CREDITS:
        view = credits_view(data)
        core = Text(f"{label} ")
        core.append(
            format_credits(view),
            style=_severity_style(view["severity"]),
        )
        opt: list[tuple[str, Text]] = [
            ("reset", Text(f"resets {view['resets_at']:%b %-d}", style="dim"))
        ]
        if note:
            opt.append(("note", Text(f"({note})", style="dim")))
        present = [name for name, _ in opt]
        line = _assemble(core, opt, present)
        while width and line.cell_len > width and present:
            for name in ["note", "reset"]:
                if name in present:
                    present.remove(name)
                    break
            line = _assemble(core, opt, present)
        if width and line.cell_len > width:
            line.truncate(width)
        line.no_wrap = True
        line.overflow = "crop"
        return line

    if shape == SHAPE_UNAVAILABLE:
        line = Text(f"{label} — no usage data", style="dim", no_wrap=True, overflow="crop")
        if width:
            line.truncate(width)
        return line

    five = data.get("five_hour") or {}
    seven = data.get("seven_day") or {}
    util5 = five.get("utilization")
    util7 = seven.get("utilization")
    resets_at = five.get("resets_at", "")

    core = _seg_five_hour(util5, label)

    # Optional segments tagged for width-driven dropping.
    seg7 = Text("7d ")
    seg7.append(format_percentage(util7), style=_usage_style(util7))
    opt: list[tuple[str, Text]] = [("7d", seg7)]

    if resets_at:
        opt.append(("reset", Text(f"reset {get_time_until_reset(resets_at)}")))

    model = _model_segment(data)
    if model:
        opt.append(("model", Text(model, style="dim")))

    credits = _credits_segment(data)
    if credits:
        opt.append(("credits", credits))

    if note:
        opt.append(("note", Text(f"({note})", style="dim")))

    present = [name for name, _ in opt]
    # Credits drop first: the segment must never displace a gauge, the reset
    # countdown, or the model breakdown on a narrow pane.
    drop_order = ["credits", "note", "model", "reset", "7d"]

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


def _window_label(minutes) -> str:
    if not isinstance(minutes, (int, float)):
        return "limit"
    if minutes % 1440 == 0:
        return f"{int(minutes // 1440)}d"
    if minutes % 60 == 0:
        return f"{int(minutes // 60)}h"
    return f"{int(minutes)}m"


def _epoch_countdown(value) -> str:
    if not isinstance(value, (int, float)):
        return ""
    seconds = max(0, int(value - datetime.now(timezone.utc).timestamp()))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes = seconds // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _individual_text(individual: dict) -> str:
    used = individual.get("used")
    limit = individual.get("limit")
    percent = individual.get("utilization")
    if used is not None and limit is not None and percent is not None:
        return f"individual {used}/{limit} ({format_percentage(percent)})"
    if percent is not None:
        return f"individual {format_percentage(percent)}"
    return ""


def build_codex_line(data: dict, *, width=None, note=None, label="Codex") -> Text:
    primary = data.get("primary")
    if not isinstance(primary, dict):
        status = _err_text(data.get("error")) if data.get("error") else "no usage data"
        line = Text(f"{label} — {status}", style="dim", no_wrap=True, overflow="crop")
        if width:
            line.truncate(width)
        return line

    util = primary.get("utilization")
    window = _window_label(primary.get("window_minutes"))
    core = Text(f"{label} {window} ")
    core.append(format_percentage(util), style=_usage_style(util))
    opt = []
    countdown = _epoch_countdown(primary.get("resets_at"))
    if countdown:
        opt.append(("reset", Text(f"reset {countdown}")))
    individual = data.get("individual_limit") or {}
    if individual.get("utilization") is not None:
        seg = Text(_individual_text(individual),
                   style=_usage_style(individual["utilization"]))
        opt.append(("individual", seg))
    if note:
        opt.append(("note", Text(f"({note})", style="dim")))
    present = [name for name, _ in opt]
    line = _assemble(core, opt, present)
    for name in ("note", "individual", "reset"):
        if width and line.cell_len > width and name in present:
            present.remove(name)
            line = _assemble(core, opt, present)
    if width and line.cell_len > width:
        line.truncate(width)
    line.no_wrap = True
    line.overflow = "crop"
    return line


def _credits_segment(data: dict) -> Text | None:
    """Spend figure for the `limits` shape, or None when there is nothing to show.

    Spec 009 resolves live buckets over credits, which hides the dollar figure
    while both are populated. This surfaces it as a droppable extra. Zero spend
    renders nothing, so a fresh month looks exactly as it did before.
    """
    view = credits_view(data)
    if not view or not view.get("used"):
        return None
    symbol = "$" if view.get("currency") == "USD" else ""
    return Text(f"{symbol}{view['used']:.2f}", style=_severity_style(view["severity"]))


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
    if detect_shape(data) == SHAPE_CREDITS:
        view = credits_view(data)
        t = Text(" ")
        t.append(format_credits(view), style=_severity_style(view["severity"]))
        return t

    util5 = (data.get("five_hour") or {}).get("utilization")
    util7 = (data.get("seven_day") or {}).get("utilization")
    t = Text(" ")
    t.append(format_percentage(util5), style=_usage_style(util5))
    t.append("  ·  7d ", style="dim")
    t.append(format_percentage(util7), style=_usage_style(util7))
    model = _model_segment(data)
    if model:
        t.append("  ·  ", style="dim")
        t.append(model, style="dim")
    credits = _credits_segment(data)
    if credits:
        t.append("  ·  ", style="dim")
        t.append_text(credits)
    return t


def build_tui_view(data: dict | None, *, note: str | None = None, label: str = "Claude"):
    """Build the full-width --tui renderable: a 5h progress bar that stretches to
    fill the pane, the stats trailing it, and the reset countdown right-aligned.

    Returns a `rich` renderable (a `Table.grid`), or the compact `build_line`
    `Text` for the not-logged-in / error states (no `five_hour` to chart).
    """
    if isinstance(data, dict) and data.get("provider") == "codex":
        primary = data.get("primary")
        if not isinstance(primary, dict):
            return build_codex_line(data, note=note, label=label)
        util = primary.get("utilization")
        stats = Text(" ")
        stats.append(format_percentage(util), style=_usage_style(util))
        individual = data.get("individual_limit") or {}
        if individual.get("utilization") is not None:
            stats.append("  ·  ", style="dim")
            stats.append(_individual_text(individual),
                         style=_usage_style(individual["utilization"]))
        countdown = _epoch_countdown(primary.get("resets_at"))
        right = Text(f" ({note})", style="dim") if note else Text(
            f" resets {countdown}" if countdown else "", style="dim")
        return _build_bar_grid(
            label=Text(f"{label}  {_window_label(primary.get('window_minutes'))} "),
            completed=min(100, max(0, util or 0)),
            style=_usage_style(util), stats=stats, right=right,
        )

    if not isinstance(data, dict) or "five_hour" not in data:
        return build_line(data, note=note, label=label)

    shape = detect_shape(data)

    if shape == SHAPE_UNAVAILABLE:
        return build_line(data, note=note, label=label)

    if shape == SHAPE_CREDITS:
        # Chart spend against the cap — the same bar Claude Code's /usage shows.
        view = credits_view(data)
        return _build_bar_grid(
            label=Text(f"{label}  "),
            completed=min(100, max(0, view["percent"] or 0)),
            style=_severity_style(view["severity"]),
            stats=_stat_segments(data),
            right=Text(f" resets {view['resets_at']:%b %-d}", style="dim")
            if not note
            else Text(f" ({note})", style="dim"),
        )

    five = data["five_hour"] or {}
    util5 = five.get("utilization")
    resets_at = five.get("resets_at", "")

    if note:
        right = Text(f" ({note})", style="dim")
    elif resets_at:
        right = Text(f" resets {get_time_until_reset(resets_at)}", style="dim")
    else:
        right = Text("")

    return _build_bar_grid(
        label=Text(f"{label}  5h "),
        completed=min(100, max(0, util5 or 0)),
        style=_usage_style(util5),
        stats=_stat_segments(data),
        right=right,
    )


def _build_bar_grid(*, label: Text, completed: float, style: str, stats: Text, right: Text):
    """Assemble the --tui row: label, stretching bar, stats, right-aligned note.

    Slack is split between the bar (3) and a spacer before the right column (1):
    the bar stretches to use most of the width, while the right note floats to
    the far right with a clean gap. Fixed columns size to their content.
    """
    grid = Table.grid(expand=True, padding=0)
    grid.add_column(no_wrap=True)                        # label
    grid.add_column(ratio=3)                             # the bar (stretches)
    grid.add_column(no_wrap=True)                        # stats
    grid.add_column(ratio=1)                             # spacer / gap
    grid.add_column(no_wrap=True, justify="right")       # reset / stale note

    bar = ProgressBar(
        total=100,
        completed=completed,
        width=None,                                       # fill the ratio column
        complete_style=style,
        finished_style=style,
        style="grey30",                                   # unfilled track
        pulse=False,
    )

    grid.add_row(label, bar, stats, Text(""), right)
    return grid


SINGLE_ACCOUNT_LABEL = "Claude"


def account_labels(accounts: list) -> list[str]:
    """Display label per account, padded to a common width.

    With one account the label stays ``Claude``, so a single-login machine
    renders exactly as it did before multi-account support (spec 011).

    With several, each line is identified by profile name and a one-letter
    account type (``max M`` / ``work E``). The letter rather than the word
    keeps the label narrow, leaving the width for the readings themselves.
    Padding to a common width keeps the bars and stats columns aligned down
    the block, since each account renders its own independent grid.
    """
    if len(accounts) <= 1:
        return [SINGLE_ACCOUNT_LABEL]
    name_width = max(len(a.name) for a in accounts)
    return [f"{a.name.ljust(name_width)} {a.type_abbrev}" for a in accounts]


def read_accounts(*, use_cache: bool, ttl: int) -> list[tuple]:
    """Fetch every configured account, returning ``(label, data, fetched_at)``.

    Each account is fetched independently so one failure stays local: an
    expired or rate-limited account renders its own error line while the
    others still show their readings.
    """
    accounts = discover_or_default()
    labels = account_labels(accounts)
    readings = []
    for account, label in zip(accounts, labels):
        if use_cache:
            data, fetched_at = fetch_usage_cached(
                ttl, account=account.name, store_dir=account.store_dir
            )
        else:
            data, fetched_at = fetch_claude_usage(account.store_dir), time.time()
        # A null reading from the cache means "nothing cached yet", not "no
        # credentials" — rendering it as "not logged in" libels a healthy
        # account whenever its gate is closed after a failure.
        if data is None and _has_credentials(account):
            data = {"error": "no_data"}
        readings.append((label, data, fetched_at))
    if is_codex_installed():
        if use_cache:
            data, fetched_at = fetch_usage_cached(
                ttl, provider="codex", fetch=fetch_codex_usage
            )
        else:
            data, fetched_at = fetch_codex_usage(), time.time()
        if data is None:
            data = {"provider": "codex", "error": "not_logged_in"}
        readings.append(("Codex", data, fetched_at))
    return readings


def _has_credentials(account) -> bool:
    """True when this account's credential file exists on disk."""
    try:
        return os.path.isfile(account.credentials_path)
    except (OSError, AttributeError):
        return False


def build_multi_line(readings: list[tuple], *, width: int | None = None) -> list[Text]:
    """One compact line per account."""
    return [
        build_line(data, width=width, label=label) for label, data, _ in readings
    ]


def build_multi_tui_view(readings: list[tuple], *, interval: int):
    """One bar row per account, stacked."""
    return Group(*[
        build_tui_view(
            data, note=_staleness_note(data, fetched_at, interval), label=label
        )
        for label, data, fetched_at in readings
    ])


def run_line(color: bool, *, use_cache: bool = True, ttl: int = 60) -> int:
    """Fetch usage once, print a single compact line, and exit.

    By default reads through the cooperative cache (``ttl`` freshness window) so
    repeated/concurrent callers don't each hit the API; ``use_cache=False`` does
    a direct per-process fetch.
    """
    log.info("starting_line_mode", cache=use_cache)
    console = Console(no_color=not color, highlight=False)
    readings = read_accounts(use_cache=use_cache, ttl=ttl)
    # soft_wrap keeps each line intact (no wrapping/cropping) for status bars.
    for line in build_multi_line(readings):
        console.print(line, soft_wrap=True)
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
                    # Rediscovered every poll so a newly logged-in profile
                    # appears without restarting the pane.
                    readings = read_accounts(use_cache=use_cache, ttl=base)
                    live.update(
                        build_multi_tui_view(readings, interval=base), refresh=True
                    )
                    time.sleep(base)
            finally:
                if prev_winch is not None:
                    signal.signal(signal.SIGWINCH, prev_winch)
    except KeyboardInterrupt:
        log.info("tui_exit")
        return 0
