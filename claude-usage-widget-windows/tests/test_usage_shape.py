"""Tests for account-shape detection (spec 009).

These encode the behavioral contract: given a usage payload, which display shape
does the widget choose, and what does it read out of it. They deliberately do
not assert on internals of the detection walk — only on the classification and
the normalized view, so the heuristic can be retuned without breaking them.
"""

from datetime import datetime

from src import usage_shape
from src.display import severity_color, COLOR_GREEN, COLOR_YELLOW, COLOR_RED

from .fixtures_usage import (
    ENTERPRISE_PAYLOAD,
    PERSONAL_PAYLOAD,
    UNAVAILABLE_PAYLOAD,
)


class TestBucketIsLive:

    def test_rejects_enterprise_placeholder(self):
        # nimbus_quill: present and a dict, but zero usage and no reset window.
        assert not usage_shape.bucket_is_live(ENTERPRISE_PAYLOAD["nimbus_quill"])

    def test_accepts_real_bucket(self):
        assert usage_shape.bucket_is_live(
            {"utilization": 70.0, "resets_at": "2026-02-16T22:00:00+00:00"}
        )

    def test_accepts_nonzero_usage_without_reset(self):
        # Escape hatch: a live bucket that omits its reset time.
        assert usage_shape.bucket_is_live({"utilization": 3.0, "resets_at": None})

    def test_rejects_none_and_non_dict(self):
        assert not usage_shape.bucket_is_live(None)
        assert not usage_shape.bucket_is_live("five_hour")
        assert not usage_shape.bucket_is_live({"utilization": None})


class TestDetectShape:

    def test_enterprise_payload_is_credits(self):
        assert usage_shape.detect_shape(ENTERPRISE_PAYLOAD) == usage_shape.SHAPE_CREDITS

    def test_personal_payload_is_limits(self):
        assert usage_shape.detect_shape(PERSONAL_PAYLOAD) == usage_shape.SHAPE_LIMITS

    def test_no_buckets_and_disabled_spend_is_unavailable(self):
        assert (
            usage_shape.detect_shape(UNAVAILABLE_PAYLOAD)
            == usage_shape.SHAPE_UNAVAILABLE
        )

    def test_buckets_win_when_both_present(self):
        both = dict(PERSONAL_PAYLOAD)
        both["spend"] = ENTERPRISE_PAYLOAD["spend"]
        assert usage_shape.detect_shape(both) == usage_shape.SHAPE_LIMITS

    def test_non_dict_is_unavailable(self):
        assert usage_shape.detect_shape(None) == usage_shape.SHAPE_UNAVAILABLE

    def test_spend_is_not_treated_as_a_bucket(self):
        # Regression guard: `spend` carries no `utilization`, but `extra_usage`
        # does — neither may be picked up by the bucket walk.
        assert usage_shape.live_buckets(ENTERPRISE_PAYLOAD) == {}


class TestCreditsView:

    def test_converts_minor_units(self):
        view = usage_shape.credits_view(ENTERPRISE_PAYLOAD)
        assert view["used"] == 2.79
        assert view["limit"] == 200.00

    def test_carries_severity_and_percent(self):
        view = usage_shape.credits_view(ENTERPRISE_PAYLOAD)
        assert view["severity"] == "normal"
        assert view["percent"] == 1

    def test_none_when_spend_disabled(self):
        assert usage_shape.credits_view(UNAVAILABLE_PAYLOAD) is None

    def test_none_when_no_spend(self):
        assert usage_shape.credits_view(PERSONAL_PAYLOAD) is None

    def test_format(self):
        view = usage_shape.credits_view(ENTERPRISE_PAYLOAD)
        assert usage_shape.format_credits(view) == "$2.79 / $200.00 (1%)"


class TestNextMonthReset:

    def test_august_rolls_to_september(self):
        assert usage_shape.next_month_reset(
            datetime(2026, 8, 25, 15, 4, 0)
        ) == datetime(2026, 9, 1, 0, 0, 0)

    def test_december_rolls_the_year(self):
        assert usage_shape.next_month_reset(
            datetime(2026, 12, 31, 23, 59, 0)
        ) == datetime(2027, 1, 1, 0, 0, 0)

    def test_month_end_does_not_overflow(self):
        # A day-31 source date must not produce an invalid Feb 31.
        assert usage_shape.next_month_reset(
            datetime(2026, 1, 31, 12, 0, 0)
        ) == datetime(2026, 2, 1, 0, 0, 0)


class TestSeverityColor:

    def test_known_severities(self):
        assert severity_color("normal") == COLOR_GREEN
        assert severity_color("warning") == COLOR_YELLOW
        assert severity_color("critical") == COLOR_RED

    def test_unknown_severity_falls_back_to_percent(self):
        assert severity_color("wat", 95) == COLOR_RED
        assert severity_color(None, 10) == COLOR_GREEN
