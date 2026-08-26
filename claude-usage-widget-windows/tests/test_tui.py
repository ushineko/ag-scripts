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


def _account(name="max", subscription_type="max"):
    """One discovered account, for pinning discovery in wiring tests."""
    from src.accounts import Account
    return Account(name=name, store_dir=f"/tmp/{name}",
                   subscription_type=subscription_type, is_default=(name == "max"))


def _pin_accounts(*accounts):
    """Patch discovery so a test does not depend on the host's real logins."""
    return mock.patch.object(tui, "discover_or_default",
                             return_value=list(accounts) or [_account()])


class TestCacheWiring:
    """--line/--tui use the cooperative cache by default; --no-cache bypasses it."""

    def test_run_line_uses_cache_by_default(self):
        with _pin_accounts(_account()), \
             mock.patch.object(tui, "fetch_usage_cached", return_value=(_data(), 0.0)) as cached, \
             mock.patch.object(tui, "fetch_claude_usage") as direct, \
             mock.patch.object(tui, "Console", lambda *a, **k: Console(file=io.StringIO())):
            tui.run_line(color=False, use_cache=True, ttl=60)
        cached.assert_called_once()
        direct.assert_not_called()

    def test_run_line_no_cache_fetches_directly(self):
        with _pin_accounts(_account()), \
             mock.patch.object(tui, "fetch_usage_cached") as cached, \
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

        with _pin_accounts(_account()), \
             mock.patch.object(tui, "fetch_usage_cached", return_value=(_data(), 0.0)) as cached, \
             mock.patch.object(tui.time, "sleep", fake_sleep), \
             mock.patch.object(tui, "Live", _DummyLive), \
             mock.patch.object(tui, "Console",
                               lambda *a, **k: Console(file=io.StringIO(), width=80)):
            rc = tui.run_tui(interval=10, color=False)

        assert rc == 0
        assert slept == [10, 10, 10]                 # fixed cadence, no per-process backoff
        # Polls the cache with the interval as TTL, addressed to the account.
        cached.assert_called_with(10, account="max", store_dir="/tmp/max")


def _spend(minor, severity="normal"):
    """A `spend` block with the given used amount in minor units."""
    return {
        "used": {"amount_minor": minor, "currency": "USD", "exponent": 2},
        "limit": {"amount_minor": 20000, "currency": "USD", "exponent": 2},
        "percent": minor // 200,
        "severity": severity,
        "enabled": True,
    }


class TestCreditsSegment:
    """Spec 010: credit spend stays visible while rate-limit gauges are live.

    Spec 009 resolves buckets over credits, which hid the dollar figure whenever
    both were populated. These lock in that it reappears, that a fresh month is
    unchanged, and that it can never displace an existing segment.
    """

    def test_spend_above_zero_shows_the_figure(self):
        d = _data(resets=True)
        d["spend"] = _spend(2567)
        assert "$25.67" in build_line(d, width=120).plain

    def test_zero_spend_shows_nothing(self):
        d = _data(resets=True)
        d["spend"] = _spend(0)
        assert "$" not in build_line(d, width=120).plain

    def test_absent_spend_key_does_not_raise(self):
        d = _data(resets=True)
        assert "$" not in build_line(d, width=120).plain

    def test_zero_spend_is_byte_identical_to_no_spend(self):
        """A fresh month must render exactly as it did before spec 010."""
        base = _data(resets=True, opus=12)
        withz = dict(base)
        withz["spend"] = _spend(0)
        assert build_line(base, width=120).plain == build_line(withz, width=120).plain

    def test_credits_drops_before_any_other_segment(self):
        """Width pressure must sacrifice the dollar figure first, never a gauge."""
        d = _data(resets=True, opus=12)
        d["spend"] = _spend(2567)
        full = build_line(d, width=200).plain
        assert "$25.67" in full
        # A width one cell short of the full line drops credits and nothing else.
        trimmed = build_line(d, width=len(full) - 1).plain
        assert "$25.67" not in trimmed
        assert "7d" in trimmed and "opus" in trimmed and "reset" in trimmed

    def test_never_overflows_requested_width(self):
        d = _data(resets=True, opus=12)
        d["spend"] = _spend(2567)
        for w in (120, 100, 60, 40, 24, 12):
            assert build_line(d, width=w).cell_len <= w

    def test_stat_segments_include_credits(self):
        d = _data(resets=True)
        d["spend"] = _spend(2567)
        assert "$25.67" in tui._stat_segments(d).plain
        d0 = _data(resets=True)
        d0["spend"] = _spend(0)
        assert "$" not in tui._stat_segments(d0).plain


class TestMultiAccountLines:
    """Spec 011: one line per configured account, each labeled."""

    def test_single_account_label_is_unchanged(self):
        assert tui.account_labels([_account()]) == ["Claude"]

    def test_multiple_accounts_are_labeled_and_padded(self):
        labels = tui.account_labels([
            _account("max", "max"),
            _account("work", "enterprise"),
        ])
        assert labels == ["max  M", "work E"]
        assert len({len(x) for x in labels}) == 1     # aligned columns

    def test_build_multi_line_emits_one_line_per_account(self):
        readings = [("max M", _data(), 0.0), ("work E", _data(), 0.0)]

        lines = tui.build_multi_line(readings)

        assert len(lines) == 2
        assert lines[0].plain.startswith("max M 5h")
        assert lines[1].plain.startswith("work E 5h")

    def test_run_line_prints_a_line_per_account(self):
        buf = io.StringIO()
        with _pin_accounts(_account("max", "max"), _account("work", "enterprise")), \
             mock.patch.object(tui, "fetch_usage_cached", return_value=(_data(), 0.0)), \
             mock.patch.object(tui, "Console",
                               lambda *a, **k: Console(file=buf, width=200, no_color=True)):
            tui.run_line(color=False, use_cache=True, ttl=60)

        printed = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
        assert len(printed) == 2
        assert printed[0].startswith("max  M")
        assert printed[1].startswith("work E")

    def test_each_account_reads_its_own_store(self):
        with _pin_accounts(_account("max", "max"), _account("work", "enterprise")), \
             mock.patch.object(tui, "fetch_usage_cached",
                               return_value=(_data(), 0.0)) as cached, \
             mock.patch.object(tui, "Console", lambda *a, **k: Console(file=io.StringIO())):
            tui.run_line(color=False, use_cache=True, ttl=60)

        stores = [c.kwargs["store_dir"] for c in cached.call_args_list]
        assert stores == ["/tmp/max", "/tmp/work"]

    def test_one_account_failing_does_not_hide_the_other(self):
        readings = [
            ("max  M", {"error": "offline"}, None),
            ("work E", _data(), 0.0),
        ]

        lines = tui.build_multi_line(readings)

        assert "offline" in lines[0].plain
        assert "5h" in lines[1].plain          # healthy account still reports

    def test_multi_tui_view_has_one_renderable_per_account(self):
        readings = [("max M", _data(), 0.0), ("work E", _data(), 0.0)]

        view = tui.build_multi_tui_view(readings, interval=60)

        assert len(view.renderables) == 2
