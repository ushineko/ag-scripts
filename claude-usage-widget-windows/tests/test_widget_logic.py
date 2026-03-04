"""Tests for display logic (no Qt required)."""

import pytest

from src.display import usage_color, format_percentage, COLOR_GREEN, COLOR_YELLOW, COLOR_RED, COLOR_GRAY


class TestUsageColor:
    """Utilization values are 0-100 (percentages from the API)."""

    def test_none_returns_gray(self):
        assert usage_color(None) == COLOR_GRAY

    def test_low_usage_green(self):
        assert usage_color(0.0) == COLOR_GREEN
        assert usage_color(25.0) == COLOR_GREEN
        assert usage_color(49.0) == COLOR_GREEN

    def test_medium_usage_yellow(self):
        assert usage_color(50.0) == COLOR_YELLOW
        assert usage_color(65.0) == COLOR_YELLOW
        assert usage_color(79.0) == COLOR_YELLOW

    def test_high_usage_red(self):
        assert usage_color(81.0) == COLOR_RED
        assert usage_color(90.0) == COLOR_RED
        assert usage_color(100.0) == COLOR_RED

    def test_boundary_80_is_yellow(self):
        assert usage_color(80.0) == COLOR_YELLOW

    def test_boundary_above_80_is_red(self):
        assert usage_color(80.1) == COLOR_RED


class TestFormatPercentage:
    """Utilization values are 0-100 (percentages from the API)."""

    def test_none_returns_dash(self):
        assert format_percentage(None) == "--"

    def test_zero(self):
        assert format_percentage(0.0) == "0%"

    def test_integer_like(self):
        assert format_percentage(42.0) == "42%"

    def test_full(self):
        assert format_percentage(100.0) == "100%"

    def test_over_100(self):
        assert format_percentage(150.0) == "150%"

    def test_fractional_rounds(self):
        assert format_percentage(26.3) == "26%"
