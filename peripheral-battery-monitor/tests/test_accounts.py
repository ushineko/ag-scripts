"""Tests for credential-store discovery and account-type labeling (spec 016).

``accounts.py`` is copied verbatim from ``claude-usage-widget-windows`` (the
same arrangement as ``usage_shape.py`` under spec 015), so these mirror that
project's suite and guard against the copy drifting.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import accounts  # noqa: E402


def _write_store(store_dir, subscription_type="max"):
    os.makedirs(store_dir, exist_ok=True)
    payload = {"claudeAiOauth": {"accessToken": "t", "subscriptionType": subscription_type}}
    with open(os.path.join(store_dir, ".credentials.json"), "w") as f:
        json.dump(payload, f)
    return store_dir


@pytest.fixture
def stores(tmp_path, monkeypatch):
    default_dir = tmp_path / "default"
    profile_root = tmp_path / "profiles"
    profile_root.mkdir()
    monkeypatch.setenv("CLAUDE_USAGE_DEFAULT_STORE", str(default_dir))
    monkeypatch.setenv(accounts.PROFILE_ROOT_ENV, str(profile_root))
    return default_dir, profile_root


class TestTypeLabel:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("free", "Free"),
            ("pro", "Pro"),
            ("max", "Max"),
            ("max_5x", "Max"),
            ("max_20x", "Max"),
            ("team", "Team"),
            ("enterprise", "Enterprise"),
        ],
    )
    def test_known_types(self, raw, expected):
        assert accounts.type_label(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "quantum_platinum"])
    def test_unknown_type_is_neutral(self, raw):
        assert accounts.type_label(raw) == accounts.UNKNOWN_TYPE_LABEL


class TestDiscover:
    def test_finds_default_and_profiles_in_stable_order(self, stores):
        default_dir, profile_root = stores
        _write_store(default_dir, "max")
        _write_store(profile_root / "work", "enterprise")
        _write_store(profile_root / "alpha", "pro")

        found = accounts.discover()

        assert [a.name for a in found] == ["max", "alpha", "work"]
        assert [a.type_label for a in found] == ["Max", "Pro", "Enterprise"]

    def test_profile_without_credentials_is_skipped(self, stores):
        default_dir, profile_root = stores
        _write_store(default_dir)
        (profile_root / "not-logged-in").mkdir()

        assert [a.name for a in accounts.discover()] == ["max"]

    def test_unreadable_store_still_counts(self, stores):
        default_dir, profile_root = stores
        _write_store(default_dir)
        broken = profile_root / "broken"
        broken.mkdir()
        (broken / ".credentials.json").write_text("{not json")

        found = accounts.discover()

        assert [a.name for a in found] == ["max", "broken"]
        assert found[1].type_label == accounts.UNKNOWN_TYPE_LABEL

    def test_discover_or_default_never_empty(self, stores):
        found = accounts.discover_or_default()

        assert len(found) == 1
        assert found[0].name == accounts.DEFAULT_PROFILE_NAME
