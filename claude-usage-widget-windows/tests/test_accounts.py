"""Tests for credential-store discovery and account-type labeling (spec 011)."""

from __future__ import annotations

import json
import os

import pytest

from src import accounts


def _write_store(store_dir, subscription_type="max"):
    """Create a credential store directory holding a minimal creds file."""
    os.makedirs(store_dir, exist_ok=True)
    payload = {"claudeAiOauth": {"accessToken": "t", "subscriptionType": subscription_type}}
    with open(os.path.join(store_dir, ".credentials.json"), "w") as f:
        json.dump(payload, f)
    return store_dir


@pytest.fixture
def stores(tmp_path, monkeypatch):
    """Point discovery at a temp default store and a temp profile root."""
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
            ("ENTERPRISE", "Enterprise"),
        ],
    )
    def test_known_types(self, raw, expected):
        assert accounts.type_label(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "quantum_platinum"])
    def test_unknown_type_is_neutral_not_an_error(self, raw):
        assert accounts.type_label(raw) == accounts.UNKNOWN_TYPE_LABEL


class TestDiscover:
    def test_finds_default_and_profiles(self, stores):
        default_dir, profile_root = stores
        _write_store(default_dir, "max")
        _write_store(profile_root / "work", "enterprise")

        found = accounts.discover()

        assert [a.name for a in found] == ["max", "work"]
        assert [a.type_label for a in found] == ["Max", "Enterprise"]

    def test_default_is_first_then_alphabetical(self, stores):
        default_dir, profile_root = stores
        _write_store(default_dir)
        for name in ("zeta", "alpha", "mid"):
            _write_store(profile_root / name)

        found = accounts.discover()

        assert [a.name for a in found] == ["max", "alpha", "mid", "zeta"]
        assert found[0].is_default is True
        assert all(a.is_default is False for a in found[1:])

    def test_profile_dir_without_credentials_is_skipped(self, stores):
        default_dir, profile_root = stores
        _write_store(default_dir)
        (profile_root / "not-logged-in").mkdir()

        assert [a.name for a in accounts.discover()] == ["max"]

    def test_missing_default_store_still_finds_profiles(self, stores):
        _, profile_root = stores
        _write_store(profile_root / "work", "enterprise")

        found = accounts.discover()

        assert [a.name for a in found] == ["work"]

    def test_missing_profile_root_is_not_an_error(self, tmp_path, monkeypatch):
        default_dir = tmp_path / "default"
        _write_store(default_dir)
        monkeypatch.setenv("CLAUDE_USAGE_DEFAULT_STORE", str(default_dir))
        monkeypatch.setenv(accounts.PROFILE_ROOT_ENV, str(tmp_path / "nope"))

        assert [a.name for a in accounts.discover()] == ["max"]

    def test_no_stores_at_all_discovers_nothing(self, stores):
        assert accounts.discover() == []

    def test_unreadable_credentials_still_counts_as_an_account(self, stores):
        default_dir, profile_root = stores
        _write_store(default_dir)
        broken = profile_root / "broken"
        broken.mkdir()
        (broken / ".credentials.json").write_text("{not json")

        found = accounts.discover()

        assert [a.name for a in found] == ["max", "broken"]
        assert found[1].subscription_type is None
        assert found[1].type_label == accounts.UNKNOWN_TYPE_LABEL

    def test_profile_named_like_the_default_does_not_duplicate(self, stores):
        default_dir, profile_root = stores
        _write_store(default_dir, "max")
        _write_store(profile_root / accounts.DEFAULT_PROFILE_NAME, "pro")

        found = accounts.discover()

        assert [a.name for a in found] == ["max"]
        assert found[0].is_default is True

    def test_file_in_profile_root_is_ignored(self, stores):
        default_dir, profile_root = stores
        _write_store(default_dir)
        (profile_root / "stray.txt").write_text("x")

        assert [a.name for a in accounts.discover()] == ["max"]


class TestAccountFields:
    def test_credentials_path_and_label(self, stores):
        default_dir, profile_root = stores
        _write_store(profile_root / "work", "enterprise")

        account = accounts.discover()[0]

        assert account.credentials_path == str(profile_root / "work" / ".credentials.json")
        assert account.label == "work Enterprise"


class TestDiscoverOrDefault:
    def test_falls_back_to_a_single_placeholder_account(self, stores):
        found = accounts.discover_or_default()

        assert len(found) == 1
        assert found[0].name == accounts.DEFAULT_PROFILE_NAME
        assert found[0].subscription_type is None

    def test_returns_real_accounts_when_present(self, stores):
        default_dir, profile_root = stores
        _write_store(default_dir, "max")
        _write_store(profile_root / "work", "enterprise")

        assert [a.name for a in accounts.discover_or_default()] == ["max", "work"]
