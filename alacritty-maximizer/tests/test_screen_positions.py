import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import get_screen_positions


def make_mock_screen(x, y, width, height):
    screen = MagicMock()
    geo = MagicMock()
    geo.x.return_value = x
    geo.y.return_value = y
    geo.width.return_value = width
    geo.height.return_value = height
    screen.geometry.return_value = geo
    size = MagicMock()
    size.width.return_value = width
    size.height.return_value = height
    screen.size.return_value = size
    return screen


def make_mock_app(screens):
    app = MagicMock()
    app.screens.return_value = screens
    return app


class TestGetScreenPositions:
    def test_single_monitor(self):
        app = make_mock_app([make_mock_screen(0, 0, 1920, 1080)])
        result = get_screen_positions(app)
        assert len(result) == 1
        assert result[0]["position_id"] == "pos-0_0"
        assert "(Left)" not in result[0]["text"]
        assert "(Right)" not in result[0]["text"]

    def test_two_monitors_side_by_side(self):
        screens = [
            make_mock_screen(0, 0, 1920, 1080),
            make_mock_screen(1920, 0, 2560, 1440),
        ]
        app = make_mock_app(screens)
        result = get_screen_positions(app)
        assert len(result) == 2
        assert result[0]["position_id"] == "pos-0_0"
        assert "(Left)" in result[0]["text"]
        assert result[1]["position_id"] == "pos-1920_0"
        assert "(Right)" in result[1]["text"]

    def test_mirrored_monitors_deduplicates(self):
        """Two monitors at the same position (mirrored) should produce one entry."""
        screens = [
            make_mock_screen(0, 0, 3840, 2160),
            make_mock_screen(0, 0, 3840, 2160),
        ]
        app = make_mock_app(screens)
        result = get_screen_positions(app)
        assert len(result) == 1
        assert result[0]["position_id"] == "pos-0_0"
        # Single effective monitor should not have position label
        assert "(Left)" not in result[0]["text"]
        assert "(Right)" not in result[0]["text"]

    def test_mirrored_monitors_keeps_higher_res(self):
        """When mirrored monitors have different resolutions, keep the larger one."""
        screens = [
            make_mock_screen(0, 0, 1920, 1080),
            make_mock_screen(0, 0, 3840, 2160),
        ]
        app = make_mock_app(screens)
        result = get_screen_positions(app)
        assert len(result) == 1
        assert "3840x2160" in result[0]["text"]

    def test_three_monitors(self):
        screens = [
            make_mock_screen(0, 0, 1920, 1080),
            make_mock_screen(1920, 0, 2560, 1440),
            make_mock_screen(4480, 0, 1920, 1080),
        ]
        app = make_mock_app(screens)
        result = get_screen_positions(app)
        assert len(result) == 3
        assert "(Left)" in result[0]["text"]
        assert "(Center)" in result[1]["text"]
        assert "(Right)" in result[2]["text"]

    def test_mirrored_pair_plus_extended(self):
        """Two mirrored monitors plus one extended should show 2 entries."""
        screens = [
            make_mock_screen(0, 0, 3840, 2160),
            make_mock_screen(0, 0, 3840, 2160),
            make_mock_screen(3840, 0, 2560, 1440),
        ]
        app = make_mock_app(screens)
        result = get_screen_positions(app)
        assert len(result) == 2
        assert result[0]["position_id"] == "pos-0_0"
        assert "(Left)" in result[0]["text"]
        assert result[1]["position_id"] == "pos-3840_0"
        assert "(Right)" in result[1]["text"]

    def test_vertical_monitor(self):
        app = make_mock_app([make_mock_screen(0, 0, 1080, 1920)])
        result = get_screen_positions(app)
        assert len(result) == 1
        assert "Vertical" in result[0]["text"]

    def test_landscape_monitor(self):
        app = make_mock_app([make_mock_screen(0, 0, 1920, 1080)])
        result = get_screen_positions(app)
        assert len(result) == 1
        assert "Landscape" in result[0]["text"]

    def test_empty_screens(self):
        app = make_mock_app([])
        result = get_screen_positions(app)
        assert len(result) == 0
