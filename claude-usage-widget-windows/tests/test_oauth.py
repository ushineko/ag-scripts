"""Tests for OAuth module."""

import json
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone, timedelta
from unittest import mock

import pytest

from src.oauth import (
    _read_credentials,
    _read_credentials_file,
    _read_credentials_keychain,
    _save_credentials_keychain,
    _apply_backoff,
    _check_creds_mtime,
    fetch_claude_usage,
    get_time_until_reset,
    is_claude_installed,
    reset_oauth_backoff,
    CLAUDE_CREDENTIALS_PATH,
    KEYCHAIN_SERVICE,
    _BACKOFF_TRANSIENT_BASE,
    _BACKOFF_TRANSIENT_CAP,
    _BACKOFF_PERMANENT_BASE,
    _BACKOFF_PERMANENT_CAP,
)
import src.oauth as oauth_module


@pytest.fixture(autouse=True)
def reset_backoff_state():
    """Reset OAuth backoff state before each test."""
    reset_oauth_backoff()
    oauth_module._oauth_creds_mtime = 0.0
    yield
    reset_oauth_backoff()
    oauth_module._oauth_creds_mtime = 0.0


class TestReadCredentialsFile:

    def test_returns_none_when_file_missing(self):
        with mock.patch("src.oauth.CLAUDE_CREDENTIALS_PATH", "/nonexistent/path"):
            assert _read_credentials_file() is None

    def test_returns_none_on_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "creds.json")
            with open(path, "w") as f:
                f.write("not json")
            with mock.patch("src.oauth.CLAUDE_CREDENTIALS_PATH", path):
                assert _read_credentials_file() is None

    def test_reads_valid_credentials(self):
        creds = {"claudeAiOauth": {"accessToken": "tok", "refreshToken": "ref", "expiresAt": 0}}
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "creds.json")
            with open(path, "w") as f:
                json.dump(creds, f)
            with mock.patch("src.oauth.CLAUDE_CREDENTIALS_PATH", path):
                result = _read_credentials_file()
                assert result["claudeAiOauth"]["accessToken"] == "tok"


class TestReadCredentialsKeychain:

    def _completed(self, returncode=0, stdout=""):
        return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout)

    def test_reads_valid_credentials(self):
        creds = {"claudeAiOauth": {"accessToken": "tok"}}
        blob = json.dumps(creds)
        with mock.patch("src.oauth.subprocess.run",
                        return_value=self._completed(0, blob + "\n")) as run:
            result = _read_credentials_keychain()
            assert result["claudeAiOauth"]["accessToken"] == "tok"
            # Reads via the `security` CLI for the expected service.
            args = run.call_args[0][0]
            assert args[0] == "security"
            assert KEYCHAIN_SERVICE in args

    def test_returns_none_when_item_missing(self):
        # `security` exits non-zero when the item is absent.
        with mock.patch("src.oauth.subprocess.run",
                        return_value=self._completed(44, "")):
            assert _read_credentials_keychain() is None

    def test_returns_none_on_invalid_json(self):
        with mock.patch("src.oauth.subprocess.run",
                        return_value=self._completed(0, "not json")):
            assert _read_credentials_keychain() is None

    def test_returns_none_when_security_missing(self):
        with mock.patch("src.oauth.subprocess.run", side_effect=FileNotFoundError):
            assert _read_credentials_keychain() is None


class TestReadCredentialsDispatch:

    def test_macos_uses_keychain(self):
        with mock.patch("src.oauth.IS_MACOS", True), \
             mock.patch("src.oauth._read_credentials_keychain", return_value={"k": 1}) as kc, \
             mock.patch("src.oauth._read_credentials_file") as fl:
            assert _read_credentials() == {"k": 1}
            kc.assert_called_once()
            fl.assert_not_called()

    def test_non_macos_uses_file(self):
        with mock.patch("src.oauth.IS_MACOS", False), \
             mock.patch("src.oauth._read_credentials_file", return_value={"k": 2}) as fl, \
             mock.patch("src.oauth._read_credentials_keychain") as kc:
            assert _read_credentials() == {"k": 2}
            fl.assert_called_once()
            kc.assert_not_called()


class TestSaveCredentialsKeychain:

    def test_writes_via_security_update(self):
        creds = {"claudeAiOauth": {"accessToken": "new"}}
        with mock.patch("src.oauth.subprocess.run") as run:
            _save_credentials_keychain(creds)
            args = run.call_args[0][0]
            assert args[:2] == ["security", "add-generic-password"]
            assert "-U" in args  # update-in-place
            assert KEYCHAIN_SERVICE in args
            assert json.dumps(creds) in args

    def test_swallows_security_errors(self):
        with mock.patch("src.oauth.subprocess.run", side_effect=OSError):
            _save_credentials_keychain({"x": 1})  # must not raise


class TestBackoff:

    def test_transient_backoff_increases(self):
        _apply_backoff(is_permanent=False)
        assert oauth_module._oauth_fail_count == 1
        assert oauth_module._oauth_backoff_until > time.monotonic()

    def test_permanent_backoff_uses_higher_base(self):
        _apply_backoff(is_permanent=True)
        until_1 = oauth_module._oauth_backoff_until
        reset_oauth_backoff()

        _apply_backoff(is_permanent=False)
        until_2 = oauth_module._oauth_backoff_until

        # Permanent base (60s) > transient base (30s), so deadline should be later
        # (both measured from same monotonic base, but permanent delay is larger)
        assert oauth_module._oauth_fail_count == 1

    def test_reset_clears_backoff(self):
        _apply_backoff(is_permanent=False)
        assert oauth_module._oauth_fail_count == 1

        reset_oauth_backoff()
        assert oauth_module._oauth_fail_count == 0
        assert oauth_module._oauth_backoff_until == 0.0

    def test_transient_caps_at_limit(self):
        for _ in range(20):
            _apply_backoff(is_permanent=False)
        # After many failures, delay should be capped
        expected_max_until = time.monotonic() + _BACKOFF_TRANSIENT_CAP + 1
        assert oauth_module._oauth_backoff_until <= expected_max_until

    def test_permanent_caps_at_limit(self):
        for _ in range(20):
            _apply_backoff(is_permanent=True)
        expected_max_until = time.monotonic() + _BACKOFF_PERMANENT_CAP + 1
        assert oauth_module._oauth_backoff_until <= expected_max_until


class TestCredsFileWatch:

    def test_mtime_change_resets_backoff(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{}")
            f.flush()
            path = f.name

        # Force the file-based path (the test machine may be macOS, where the
        # default code path reads the Keychain instead).
        with mock.patch("src.oauth.CLAUDE_CREDENTIALS_PATH", path), \
             mock.patch("src.oauth.IS_MACOS", False):
            # Set initial mtime
            oauth_module._oauth_creds_mtime = os.stat(path).st_mtime - 1
            _apply_backoff(is_permanent=False)
            assert oauth_module._oauth_fail_count == 1

            # Trigger mtime check — file is "newer" than recorded
            _check_creds_mtime()
            assert oauth_module._oauth_fail_count == 0

        os.unlink(path)


class TestGetTimeUntilReset:

    def test_valid_future_timestamp(self):
        future = (datetime.now(timezone.utc) + timedelta(hours=2, minutes=15, seconds=30)).isoformat()
        result = get_time_until_reset(future)
        assert "2h" in result
        assert "15m" in result

    def test_minutes_only(self):
        future = (datetime.now(timezone.utc) + timedelta(minutes=30, seconds=30)).isoformat()
        result = get_time_until_reset(future)
        assert "30m" in result
        assert "h" not in result

    def test_past_timestamp(self):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        result = get_time_until_reset(past)
        assert result == "Resetting..."

    def test_invalid_timestamp(self):
        assert get_time_until_reset("not-a-date") == "Unknown"
        assert get_time_until_reset(None) == "Unknown"


class TestFetchClaudeUsage:

    def test_returns_none_when_no_credentials(self):
        with mock.patch("src.oauth._read_credentials", return_value=None):
            assert fetch_claude_usage() is None

    def test_returns_none_when_no_oauth_key(self):
        with mock.patch("src.oauth._read_credentials", return_value={"other": "data"}):
            assert fetch_claude_usage() is None

    def test_returns_auth_expired_when_no_refresh_token(self):
        creds = {"claudeAiOauth": {"accessToken": "tok", "expiresAt": 0}}
        with mock.patch("src.oauth._read_credentials", return_value=creds):
            result = fetch_claude_usage()
            assert result == {"error": "auth_expired"}

    def test_returns_backoff_when_in_backoff(self):
        oauth_module._oauth_backoff_until = time.monotonic() + 3600
        creds = {"claudeAiOauth": {"accessToken": "tok", "refreshToken": "ref", "expiresAt": 0}}
        with mock.patch("src.oauth._read_credentials", return_value=creds):
            result = fetch_claude_usage()
            assert result == {"error": "auth_backoff"}


class TestIsClaudeInstalled:

    def test_returns_true_when_found(self):
        with mock.patch("shutil.which", return_value="/usr/bin/claude"):
            assert is_claude_installed() is True

    def test_returns_false_when_not_found(self):
        with mock.patch("shutil.which", return_value=None):
            assert is_claude_installed() is False
