#!/usr/bin/env python3
"""Unit tests for the VDF parser and Steam library scanning."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from steam_desktop_creator import parse_vdf, SteamGame, FILTERED_APPIDS


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


class TestSteamGame:
    """Tests for the SteamGame dataclass."""

    def test_desktop_file_path(self):
        """Test desktop file path generation."""
        game = SteamGame(
            appid=400,
            name="Portal",
            install_dir="Portal",
            library_path=Path("/mnt/games")
        )
        assert "steam-game-400.desktop" in str(game.desktop_file_path)

    def test_icon_name(self):
        """Test icon name generation."""
        game = SteamGame(
            appid=400,
            name="Portal",
            install_dir="Portal",
            library_path=Path("/mnt/games")
        )
        assert game.icon_name == "steam-game-400"


class TestFilteredAppids:
    """Tests for the filtered appids list."""

    def test_proton_filtered(self):
        """Test that Proton is in the filtered list."""
        assert 1493710 in FILTERED_APPIDS  # Proton Experimental

    def test_runtime_filtered(self):
        """Test that Steam Linux Runtime is filtered."""
        assert 1070560 in FILTERED_APPIDS  # Steam Linux Runtime 1.0
        assert 1628350 in FILTERED_APPIDS  # Steam Linux Runtime 3.0

    def test_redistributables_filtered(self):
        """Test that Steamworks redistributables are filtered."""
        assert 228980 in FILTERED_APPIDS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
