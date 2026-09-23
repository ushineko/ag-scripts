"""Codex section formatting helpers."""

from codex_section import reset_countdown, usage_color, window_label


def test_window_label_preserves_server_duration():
    assert window_label(10080) == "7d"
    assert window_label(300) == "5h"
    assert window_label(90) == "90m"


def test_usage_color_matches_existing_usage_thresholds():
    assert usage_color(49) == "#22c55e"
    assert usage_color(50) == "#eab308"
    assert usage_color(81) == "#ef4444"


def test_reset_countdown_is_non_negative():
    assert reset_countdown(0) == "0m"
