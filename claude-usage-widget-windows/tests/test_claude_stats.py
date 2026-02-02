"""Tests for claude_stats module."""

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import pytest

from src.claude_stats import (
    get_session_window,
    get_time_until_reset,
    get_claude_stats,
    format_tokens,
    calculate_usage_percentage,
    get_usage_color,
)
from src.config import (
    DEFAULTS,
    load_config,
    save_config,
    get_setting,
    set_setting,
)


class TestSessionWindow:
    """Tests for session window calculations."""

    def test_window_hours_4_reset_2(self):
        """Test 4-hour window with reset at 2:00."""
        # Mock time to 10:30 AM
        with mock.patch("src.claude_stats.datetime") as mock_dt:
            mock_now = datetime(2024, 1, 15, 10, 30, 0)
            mock_now = mock_now.astimezone()
            mock_dt.now.return_value = mock_now

            window_start, window_end = get_session_window(window_hours=4, reset_hour=2)

            # At 10:30, window should be 10:00-14:00
            assert window_end.hour == 14
            assert window_start.hour == 10

    def test_window_hours_1_reset_0(self):
        """Test 1-hour window with reset at midnight."""
        with mock.patch("src.claude_stats.datetime") as mock_dt:
            mock_now = datetime(2024, 1, 15, 15, 45, 0)
            mock_now = mock_now.astimezone()
            mock_dt.now.return_value = mock_now

            window_start, window_end = get_session_window(window_hours=1, reset_hour=0)

            # At 15:45, window should be 15:00-16:00
            assert window_end.hour == 16
            assert window_start.hour == 15

    def test_window_crosses_midnight(self):
        """Test window that crosses midnight."""
        with mock.patch("src.claude_stats.datetime") as mock_dt:
            mock_now = datetime(2024, 1, 15, 23, 30, 0)
            mock_now = mock_now.astimezone()
            mock_dt.now.return_value = mock_now

            window_start, window_end = get_session_window(window_hours=4, reset_hour=2)

            # At 23:30, window should be 22:00-02:00 (next day)
            assert window_start.hour == 22
            assert window_end.hour == 2
            assert window_end.day == 16  # Next day


class TestTimeUntilReset:
    """Tests for time until reset formatting."""

    def test_hours_and_minutes(self):
        """Test formatting with hours and minutes."""
        now = datetime.now().astimezone()
        window_start = now - timedelta(hours=1)
        window_end = now + timedelta(hours=2, minutes=30)

        window_str, countdown_str, hours, minutes = get_time_until_reset(
            window_start, window_end
        )

        assert "2h" in countdown_str
        assert hours == 2
        assert minutes == 30

    def test_minutes_only(self):
        """Test formatting with only minutes."""
        now = datetime.now().astimezone()
        window_start = now - timedelta(hours=3)
        window_end = now + timedelta(minutes=45)

        window_str, countdown_str, hours, minutes = get_time_until_reset(
            window_start, window_end
        )

        assert "h" not in countdown_str
        assert "45m" in countdown_str
        assert hours == 0
        assert minutes == 45

    def test_window_str_format(self):
        """Test window string format."""
        window_start = datetime(2024, 1, 15, 10, 0, 0).astimezone()
        window_end = datetime(2024, 1, 15, 14, 0, 0).astimezone()

        window_str, _, _, _ = get_time_until_reset(window_start, window_end)

        assert "10:00" in window_str
        assert "14:00" in window_str


class TestFormatTokens:
    """Tests for token formatting."""

    def test_small_numbers(self):
        """Test numbers under 1000."""
        assert format_tokens(0) == "0"
        assert format_tokens(500) == "500"
        assert format_tokens(999) == "999"

    def test_thousands(self):
        """Test numbers in thousands."""
        assert format_tokens(1000) == "1.0k"
        assert format_tokens(1500) == "1.5k"
        assert format_tokens(250000) == "250.0k"
        assert format_tokens(999999) == "1000.0k"

    def test_millions(self):
        """Test numbers in millions."""
        assert format_tokens(1000000) == "1.0M"
        assert format_tokens(1500000) == "1.5M"
        assert format_tokens(2500000) == "2.5M"


class TestCalculateUsagePercentage:
    """Tests for usage percentage calculation."""

    def test_basic_percentage(self):
        """Test basic percentage calculation."""
        # 50% of 500k budget
        pct = calculate_usage_percentage(250000, budget=500000, offset=0)
        assert pct == 50.0

    def test_with_offset(self):
        """Test percentage with offset adjustment."""
        # 200k tokens + 50k offset = 250k, which is 50% of 500k
        pct = calculate_usage_percentage(200000, budget=500000, offset=50000)
        assert pct == 50.0

    def test_caps_at_100(self):
        """Test that percentage caps at 100%."""
        pct = calculate_usage_percentage(1000000, budget=500000, offset=0)
        assert pct == 100.0

    def test_zero_budget(self):
        """Test handling of zero budget."""
        pct = calculate_usage_percentage(100000, budget=0, offset=0)
        assert pct == 0.0


class TestGetUsageColor:
    """Tests for usage color determination."""

    def test_green_zone(self):
        """Test green color for low usage."""
        assert get_usage_color(0) == "green"
        assert get_usage_color(25) == "green"
        assert get_usage_color(49.9) == "green"

    def test_yellow_zone(self):
        """Test yellow color for medium usage."""
        assert get_usage_color(50) == "yellow"
        assert get_usage_color(65) == "yellow"
        assert get_usage_color(79.9) == "yellow"

    def test_red_zone(self):
        """Test red color for high usage."""
        assert get_usage_color(80) == "red"
        assert get_usage_color(90) == "red"
        assert get_usage_color(100) == "red"


class TestConfig:
    """Tests for configuration management."""

    def test_defaults(self):
        """Test default values exist."""
        assert "session_budget" in DEFAULTS
        assert "window_hours" in DEFAULTS
        assert "reset_hour" in DEFAULTS
        assert "token_offset" in DEFAULTS

    def test_save_and_load(self):
        """Test saving and loading config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("src.config.get_config_dir", return_value=Path(tmpdir)):
                # Save custom config
                custom_config = {**DEFAULTS, "session_budget": 750000}
                save_config(custom_config)

                # Load and verify
                loaded = load_config()
                assert loaded["session_budget"] == 750000

    def test_get_setting_default(self):
        """Test getting setting with default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("src.config.get_config_dir", return_value=Path(tmpdir)):
                # Get setting that doesn't exist
                value = get_setting("nonexistent", default=42)
                assert value == 42

    def test_set_setting(self):
        """Test setting individual values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("src.config.get_config_dir", return_value=Path(tmpdir)):
                set_setting("session_budget", 1000000)
                assert get_setting("session_budget") == 1000000


class TestClaudeStats:
    """Tests for Claude stats parsing."""

    def test_no_projects_dir(self):
        """Test handling of missing projects directory."""
        with mock.patch("src.claude_stats.get_claude_projects_dir") as mock_dir:
            mock_dir.return_value = Path("/nonexistent/path")
            stats = get_claude_stats()
            assert stats is None

    def test_parse_jsonl_files(self):
        """Test parsing JSONL session files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            projects_path = Path(tmpdir)

            # Create a mock JSONL file
            jsonl_content = [
                {
                    "timestamp": datetime.now().isoformat(),
                    "message": {
                        "usage": {
                            "input_tokens": 1000,
                            "output_tokens": 500,
                            "cache_read_input_tokens": 200,
                            "cache_creation_input_tokens": 100,
                        }
                    },
                },
                {
                    "timestamp": datetime.now().isoformat(),
                    "message": {
                        "usage": {
                            "input_tokens": 2000,
                            "output_tokens": 1000,
                            "cache_read_input_tokens": 300,
                            "cache_creation_input_tokens": 150,
                        }
                    },
                },
            ]

            # Create project directory with JSONL file
            project_dir = projects_path / "test-project"
            project_dir.mkdir()
            jsonl_file = project_dir / "session.jsonl"

            with open(jsonl_file, "w") as f:
                for entry in jsonl_content:
                    f.write(json.dumps(entry) + "\n")

            # Mock the projects path
            with mock.patch(
                "src.claude_stats.get_claude_projects_dir", return_value=projects_path
            ):
                # Get stats without window filtering
                window_start = datetime.now().astimezone() - timedelta(hours=1)
                window_end = datetime.now().astimezone() + timedelta(hours=1)
                stats = get_claude_stats(window_start, window_end)

                assert stats is not None
                assert stats["input_tokens"] == 3000  # 1000 + 2000
                assert stats["output_tokens"] == 1500  # 500 + 1000
                assert stats["session_tokens"] == 4500  # 3000 + 1500
                assert stats["cache_read"] == 500  # 200 + 300
                assert stats["cache_create"] == 250  # 100 + 150
                assert stats["api_calls"] == 2
                assert stats["files_processed"] == 1

    def test_handles_malformed_json(self):
        """Test handling of malformed JSON lines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            projects_path = Path(tmpdir)
            project_dir = projects_path / "test-project"
            project_dir.mkdir()
            jsonl_file = project_dir / "session.jsonl"

            # Use current timestamps so they fall within the window
            now = datetime.now().isoformat()

            # Write mix of valid and invalid JSON
            with open(jsonl_file, "w") as f:
                f.write(f'{{"timestamp": "{now}", "message": {{"usage": {{"input_tokens": 1000, "output_tokens": 500}}}}}}\n')
                f.write("this is not valid json\n")
                f.write(f'{{"timestamp": "{now}", "message": {{"usage": {{"input_tokens": 2000, "output_tokens": 1000}}}}}}\n')

            with mock.patch(
                "src.claude_stats.get_claude_projects_dir", return_value=projects_path
            ):
                window_start = datetime.now().astimezone() - timedelta(days=1)
                window_end = datetime.now().astimezone() + timedelta(days=1)
                stats = get_claude_stats(window_start, window_end)

                # Should still get stats from valid lines
                assert stats is not None
                assert stats["api_calls"] == 2


class TestCalibration:
    """Tests for calibration calculations."""

    def test_budget_adjustment(self):
        """Test budget adjustment calculation."""
        # If we have 250k tokens and want to show 50%, budget should be 500k
        current_tokens = 250000
        target_percentage = 50
        new_budget = int(current_tokens / (target_percentage / 100))
        assert new_budget == 500000

    def test_offset_adjustment(self):
        """Test offset adjustment calculation."""
        # With 500k budget, 50% = 250k tokens
        # If we currently show 200k, offset should be +50k
        budget = 500000
        current_tokens = 200000
        target_percentage = 50
        target_tokens = int(budget * target_percentage / 100)
        new_offset = target_tokens - current_tokens
        assert new_offset == 50000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
