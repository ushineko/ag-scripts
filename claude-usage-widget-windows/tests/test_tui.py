"""Tests for the terminal (TUI) rendering logic.

Rendering uses `rich`: ``build_line`` returns a styled ``rich.text.Text`` and the
``Console`` decides whether to emit color. The self-refreshing loop (``run_tui``)
is exercised with `rich.live.Live` patched out; the rendering it relies on is
covered directly.
"""

import io
import time
from unittest import mock

from rich.console import Console

import src.tui as tui
from src.tui import build_line, build_tui_view

# A future timestamp keeps the reset countdown deterministic (always positive).
FUTURE = "2099-01-01T00:00:00+00:00"


def _data(util5=47, util7=31, resets=False, opus=0, sonnet=0):
    d = {
        "five_hour": {"utilization": util5},
        "seven_day": {"utilization": util7},
    }
    if resets:
        d["five_hour"]["resets_at"] = FUTURE
    if opus:
        d["seven_day_opus"] = {"utilization": opus}
    if sonnet:
        d["seven_day_sonnet"] = {"utilization": sonnet}
    return d


def _styles(text):
    """Set of style names applied to spans of a rich Text."""
    return {span.style for span in text.spans}


def _render(text, *, color):
    """Render a Text through a Console and return the raw output (with codes)."""
    buf = io.StringIO()
    Console(
        file=buf, force_terminal=True, no_color=not color,
        color_system="standard", width=200,
    ).print(text, soft_wrap=True)
    return buf.getvalue()


class TestBuildLine:

    def test_normal_line_content(self):
        line = build_line(_data())
        assert "Claude" in line.plain
        assert "5h 47%" in line.plain
        assert "7d 31%" in line.plain

    def test_color_thresholds_as_styles(self):
        assert "green" in _styles(build_line(_data(util5=47)))
        assert "yellow" in _styles(build_line(_data(util5=60)))
        assert "red" in _styles(build_line(_data(util5=95)))

    def test_unknown_utilization_renders_dashes(self):
        assert "5h --" in build_line(_data(util5=None)).plain

    def test_reset_countdown_present(self):
        assert "reset" in build_line(_data(resets=True)).plain

    def test_model_breakdown(self):
        line = build_line(_data(opus=12, sonnet=19))
        assert "opus 12%" in line.plain
        assert "sonnet 19%" in line.plain

    def test_zero_model_buckets_omitted(self):
        line = build_line(_data(opus=0, sonnet=0))
        assert "opus" not in line.plain
        assert "sonnet" not in line.plain

    def test_note_appended(self):
        line = build_line(_data(), note="rate limited · 3m ago")
        assert "(rate limited · 3m ago)" in line.plain


class TestColorEmission:
    """Color lives as styles on the Text; the Console gates the actual codes."""

    def test_color_on_emits_ansi(self):
        out = _render(build_line(_data(util5=47)), color=True)
        assert "\x1b[32m" in out  # green

    def test_color_off_suppresses_ansi(self):
        out = _render(build_line(_data(util5=47)), color=False)
        assert "\x1b[32m" not in out
        assert "\x1b[31m" not in out  # no red either


def _render_plain(renderable, width=120):
    """Render any rich renderable to a plain (no-color) string at a fixed width."""
    buf = io.StringIO()
    Console(file=buf, no_color=True, width=width).print(renderable)
    return buf.getvalue()


class TestBuildTuiView:
    """The full-width --tui view: a stretching 5h bar, trailing stats, and a
    right-aligned reset countdown."""

    def test_renders_bar_stats_and_reset(self):
        out = _render_plain(build_tui_view(_data(resets=True, sonnet=12)))
        assert "Claude  5h" in out
        assert "━" in out               # rich progress bar
        assert "47%" in out
        assert "7d 31%" in out
        assert "sonnet 12%" in out
        assert "resets" in out

    def test_bar_stretches_to_fill_width(self):
        # The rendered row should span (close to) the full console width.
        line = _render_plain(build_tui_view(_data(resets=True)), width=120).splitlines()[0]
        assert len(line) >= 100

    def test_stale_note_replaces_reset(self):
        out = _render_plain(build_tui_view(_data(resets=True), note="offline · 3m ago"))
        assert "(offline · 3m ago)" in out
        assert "resets" not in out

    def test_error_falls_back_to_compact_line(self):
        assert "not logged in" in _render_plain(build_tui_view(None))
        assert "rate limited" in _render_plain(build_tui_view({"error": "rate_limited"}))


class TestErrorStates:

    def test_not_logged_in(self):
        line = build_line(None)
        assert "Claude" in line.plain
        assert "not logged in" in line.plain

    def test_error_dict(self):
        assert "rate limited" in build_line({"error": "rate_limited"}).plain

    def test_offline_error(self):
        assert "offline" in build_line({"error": "offline"}).plain


class TestWidthTruncation:

    def test_5h_always_survives(self):
        line = build_line(_data(resets=True, opus=12, sonnet=19), width=18)
        assert "47%" in line.plain
        assert line.cell_len <= 18

    def test_model_dropped_before_seven_day(self):
        line = build_line(_data(opus=12, sonnet=19), width=24)
        assert "7d 31%" in line.plain
        assert "opus" not in line.plain
        assert line.cell_len <= 24

    def test_drops_to_core_when_very_narrow(self):
        line = build_line(_data(resets=True, opus=12, sonnet=19), width=15)
        assert "5h 47%" in line.plain
        assert "7d" not in line.plain
        assert line.cell_len <= 15

    def test_no_truncation_when_width_none(self):
        line = build_line(_data(resets=True, opus=12, sonnet=19), width=None)
        assert "opus 12%" in line.plain
        assert "sonnet 19%" in line.plain


class _DummyLive:
    """Stand-in for rich.live.Live: a no-op context manager with .update()."""

    def __init__(self, *a, **k):
        self.frames = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def update(self, renderable, **k):
        self.frames.append(renderable)


class TestCacheWiring:
    """--line/--tui use the cooperative cache by default; --no-cache bypasses it."""

    def test_run_line_uses_cache_by_default(self):
        with mock.patch.object(tui, "fetch_usage_cached", return_value=(_data(), 0.0)) as cached, \
             mock.patch.object(tui, "fetch_claude_usage") as direct, \
             mock.patch.object(tui, "Console", lambda *a, **k: Console(file=io.StringIO())):
            tui.run_line(color=False, use_cache=True, ttl=60)
        cached.assert_called_once()
        direct.assert_not_called()

    def test_run_line_no_cache_fetches_directly(self):
        with mock.patch.object(tui, "fetch_usage_cached") as cached, \
             mock.patch.object(tui, "fetch_claude_usage", return_value=_data()) as direct, \
             mock.patch.object(tui, "Console", lambda *a, **k: Console(file=io.StringIO())):
            tui.run_line(color=False, use_cache=False, ttl=60)
        direct.assert_called_once()
        cached.assert_not_called()


class TestStalenessNote:
    """run_tui marks a reading stale (from the shared cache age) past ~1.5x interval."""

    def test_fresh_reading_has_no_note(self):
        assert tui._staleness_note(_data(), time.time(), 60) is None

    def test_old_reading_is_marked_cached(self):
        note = tui._staleness_note(_data(), time.time() - 600, 60)
        assert note is not None and note.startswith("cached")

    def test_no_note_without_fetched_at(self):
        assert tui._staleness_note(_data(), None, 60) is None

    def test_no_note_for_error_payload(self):
        assert tui._staleness_note({"error": "offline"}, time.time() - 600, 60) is None


class TestRunTuiLoop:
    """The live loop polls at a fixed interval (the cache gate, not run_tui, does
    the API throttling/backoff) and exits cleanly on Ctrl-C."""

    def test_polls_cache_at_fixed_interval_and_exits(self):
        slept = []

        def fake_sleep(secs):
            slept.append(secs)
            if len(slept) >= 3:
                raise KeyboardInterrupt

        with mock.patch.object(tui, "fetch_usage_cached", return_value=(_data(), 0.0)) as cached, \
             mock.patch.object(tui.time, "sleep", fake_sleep), \
             mock.patch.object(tui, "Live", _DummyLive), \
             mock.patch.object(tui, "Console",
                               lambda *a, **k: Console(file=io.StringIO(), width=80)):
            rc = tui.run_tui(interval=10, color=False)

        assert rc == 0
        assert slept == [10, 10, 10]                 # fixed cadence, no per-process backoff
        cached.assert_called_with(10)                 # polls the cache with the interval as TTL
