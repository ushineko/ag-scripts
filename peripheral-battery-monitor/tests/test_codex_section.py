"""Codex section formatting helpers."""

from codex_section import reported_amount, reset_countdown, usage_color, window_label


def test_window_label_preserves_server_duration():
    assert window_label(10080) == "7d"
    assert window_label(300) == "5h"
    assert window_label(90) == "90m"


def test_usage_color_matches_existing_usage_thresholds():
    assert usage_color(49) == "#4caf50"
    assert usage_color(50) == "#ff9800"
    assert usage_color(81) == "#f44336"


def test_reset_countdown_is_non_negative():
    assert reset_countdown(0) == "0m"


def test_reported_amount_is_compact_and_does_not_invent_currency():
    assert reported_amount("403.51035809516907") == "403.51"
    assert reported_amount("1200") == "1200"
