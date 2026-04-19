"""Shared fixtures for vscode-launcher tests."""

import sys
from pathlib import Path

import pytest

# Make the package importable without installation
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication instance for the test session."""
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def temp_config_file(tmp_path):
    return tmp_path / "workspaces.json"


@pytest.fixture
def sample_workspace_dict():
    return {
        "id": "abc12345",
        "label": "platform-backend",
        "path": "/home/user/git/platform-backend",
        "tmux_session": "platform-backend",
    }


@pytest.fixture
def sample_config(sample_workspace_dict):
    return {
        "version": 1,
        "workspaces": [sample_workspace_dict],
        "window_geometry": {"x": 120, "y": 80, "w": 800, "h": 600},
    }
