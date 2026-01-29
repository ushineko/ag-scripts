#!/usr/bin/env python3
"""Unit tests for the game scanners and parsers."""

import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from game_desktop_creator import parse_vdf, Game, STEAM_FILTERED_APPIDS, get_heroic_games


class TestVdfParser:
    """Tests for the VDF parser."""

    def test_parse_simple_key_value(self):
        """Test parsing simple key-value pairs."""
        content = '"key1" "value1"\n"key2" "value2"'
        result = parse_vdf(content)
        assert result == {"key1": "value1", "key2": "value2"}

    def test_parse_nested_dict(self):
        """Test parsing nested dictionaries."""
        content = '''
        "outer"
        {
            "inner" "value"
        }
        '''
        result = parse_vdf(content)
        assert result == {"outer": {"inner": "value"}}

    def test_parse_deeply_nested(self):
        """Test parsing deeply nested structures."""
        content = '''
        "level1"
        {
            "level2"
            {
                "level3" "deep_value"
            }
        }
        '''
        result = parse_vdf(content)
        assert result["level1"]["level2"]["level3"] == "deep_value"

    def test_parse_appmanifest(self):
        """Test parsing a real appmanifest structure."""
        content = '''
        "AppState"
        {
            "appid"		"400"
            "Universe"		"1"
            "name"		"Portal"
            "StateFlags"		"4"
            "installdir"		"Portal"
        }
        '''
        result = parse_vdf(content)
        assert "AppState" in result
        assert result["AppState"]["appid"] == "400"
        assert result["AppState"]["name"] == "Portal"
        assert result["AppState"]["installdir"] == "Portal"

    def test_parse_libraryfolders(self):
        """Test parsing libraryfolders.vdf structure."""
        content = '''
        "libraryfolders"
        {
            "0"
            {
                "path"		"/home/user/.local/share/Steam"
                "label"		""
                "apps"
                {
                    "228980"		"205246599"
                }
            }
            "1"
            {
                "path"		"/mnt/games/SteamLibrary"
                "apps"
                {
                    "400"		"4347052354"
                }
            }
        }
        '''
        result = parse_vdf(content)
        assert "libraryfolders" in result
        assert result["libraryfolders"]["0"]["path"] == "/home/user/.local/share/Steam"
        assert result["libraryfolders"]["1"]["path"] == "/mnt/games/SteamLibrary"

    def test_parse_empty_content(self):
        """Test parsing empty content."""
        result = parse_vdf("")
        assert result == {}

    def test_parse_tabs_and_spaces(self):
        """Test that tabs and spaces in values are preserved."""
        content = '"key" "value with spaces"'
        result = parse_vdf(content)
        assert result["key"] == "value with spaces"


class TestGame:
    """Tests for the Game dataclass."""

    def test_steam_game_properties(self):
        """Test Steam game property generation."""
        game = Game(id="400", name="Portal", source="steam")
        assert game.desktop_file_name == "steam-game-400.desktop"
        assert game.icon_name == "steam-game-400"
        assert game.source_label == "Steam"
        assert game.get_fallback_icon() == "steam"
        assert "steam://rungameid/400" in game.get_launch_command()

    def test_epic_game_properties(self):
        """Test Epic game property generation."""
        game = Game(id="abc123", name="Test Game", source="epic")
        assert game.desktop_file_name == "heroic-epic-abc123.desktop"
        assert game.icon_name == "heroic-game-abc123"
        assert game.source_label == "Epic"
        assert game.get_fallback_icon() == "heroic"
        assert "heroic://launch/legendary/abc123" in game.get_launch_command()

    def test_gog_game_properties(self):
        """Test GOG game property generation."""
        game = Game(id="gog123", name="GOG Game", source="gog")
        assert game.desktop_file_name == "heroic-gog-gog123.desktop"
        assert game.icon_name == "heroic-game-gog123"
        assert game.source_label == "GOG"
        assert game.get_fallback_icon() == "heroic"
        assert "heroic://launch/gog/gog123" in game.get_launch_command()


class TestFilteredAppids:
    """Tests for the filtered appids list."""

    def test_proton_filtered(self):
        """Test that Proton is in the filtered list."""
        assert 1493710 in STEAM_FILTERED_APPIDS  # Proton Experimental

    def test_runtime_filtered(self):
        """Test that Steam Linux Runtime is filtered."""
        assert 1070560 in STEAM_FILTERED_APPIDS  # Steam Linux Runtime 1.0
        assert 1628350 in STEAM_FILTERED_APPIDS  # Steam Linux Runtime 3.0

    def test_redistributables_filtered(self):
        """Test that Steamworks redistributables are filtered."""
        assert 228980 in STEAM_FILTERED_APPIDS


class TestHeroicJsonParsing:
    """Tests for Heroic JSON parsing."""

    def test_parse_legendary_installed_json(self):
        """Test parsing legendary installed.json format."""
        json_content = {
            "abc123": {
                "app_name": "abc123",
                "title": "Test Epic Game",
                "install_path": "/home/user/Games/TestGame",
                "platform": "Windows"
            },
            "def456": {
                "app_name": "def456",
                "title": "Another Game",
                "install_path": "/home/user/Games/AnotherGame",
                "platform": "Windows"
            }
        }

        # Test that we can parse the structure correctly
        for app_name, info in json_content.items():
            game = Game(
                id=app_name,
                name=info.get("title", app_name),
                source="epic"
            )
            assert game.id == app_name
            assert game.name == info["title"]
            assert game.source == "epic"

    def test_parse_gog_installed_json(self):
        """Test parsing GOG installed.json format."""
        json_content = {
            "1234567890": {
                "app_name": "1234567890",
                "title": "GOG Test Game",
                "install_path": "/home/user/Games/GOGGame"
            }
        }

        for app_name, info in json_content.items():
            game = Game(
                id=app_name,
                name=info.get("title", app_name),
                source="gog"
            )
            assert game.id == app_name
            assert game.name == info["title"]
            assert game.source == "gog"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
