from __future__ import annotations

import pytest

from slack_presence_toggle.slack_client import (
    ApiHealth,
    AuthInfo,
    PresenceState,
    ProfileStatus,
    SlackClient,
)


class FakeTransport:
    """Records calls and returns canned responses keyed by method name."""

    def __init__(self, responses: dict | None = None):
        self.responses = responses or {}
        self.calls: list[tuple[str, dict, bool]] = []

    def __call__(self, method: str, params: dict, json_body: bool) -> dict:
        self.calls.append((method, dict(params), json_body))
        if method not in self.responses:
            raise AssertionError(f"unexpected method {method!r} called")
        return self.responses[method]


def _client(responses):
    transport = FakeTransport(responses)
    return SlackClient("xoxp-test", transport=transport), transport


def test_auth_test_success():
    c, t = _client({"auth.test": {
        "ok": True, "user": "alice", "team": "Acme",
        "user_id": "U1", "team_id": "T1",
    }})
    health, info = c.auth_test()
    assert health.ok
    assert info == AuthInfo(user="alice", team="Acme", user_id="U1", team_id="T1")
    assert t.calls == [("auth.test", {}, False)]


def test_auth_test_token_revoked():
    c, _ = _client({"auth.test": {"ok": False, "error": "token_revoked"}})
    health, info = c.auth_test()
    assert not health.ok
    assert health.error == "token_revoked"
    assert info is None


def test_get_presence_parsed_completely():
    c, _ = _client({"users.getPresence": {
        "ok": True, "presence": "active", "online": True,
        "auto_away": False, "manual_away": False,
        "connection_count": 3, "last_activity": 1700000000,
    }})
    health, state = c.get_presence()
    assert health.ok
    assert state == PresenceState(
        presence="active", online=True, auto_away=False, manual_away=False,
        connection_count=3, last_activity=1700000000,
    )


def test_get_presence_handles_missing_optional_fields():
    c, _ = _client({"users.getPresence": {"ok": True, "presence": "away"}})
    _, state = c.get_presence()
    assert state.presence == "away"
    assert state.online is False
    assert state.connection_count == 0


def test_set_presence_form_encoded():
    c, t = _client({"users.setPresence": {"ok": True}})
    health = c.set_presence("away")
    assert health.ok
    assert t.calls == [("users.setPresence", {"presence": "away"}, False)]


def test_set_presence_rejects_invalid_value():
    c, _ = _client({})
    with pytest.raises(ValueError):
        c.set_presence("offline")  # type: ignore[arg-type]


def test_set_profile_status_uses_json_body():
    c, t = _client({"users.profile.set": {"ok": True}})
    health = c.set_profile_status("Heads down", ":dart:", 1700000060)
    assert health.ok
    method, params, json_body = t.calls[0]
    assert method == "users.profile.set"
    assert json_body is True
    assert params == {
        "profile": {
            "status_text": "Heads down",
            "status_emoji": ":dart:",
            "status_expiration": 1700000060,
        }
    }


def test_get_profile_status_parses():
    c, _ = _client({"users.profile.get": {
        "ok": True,
        "profile": {
            "status_text": "Heads down",
            "status_emoji": ":dart:",
            "status_expiration": 1700000060,
            "real_name": "Alice",
        },
    }})
    health, status = c.get_profile_status()
    assert health.ok
    assert status == ProfileStatus(text="Heads down", emoji=":dart:", expiration=1700000060)


def test_get_profile_status_empty_profile_section():
    c, _ = _client({"users.profile.get": {"ok": True, "profile": {}}})
    _, status = c.get_profile_status()
    assert status == ProfileStatus(text="", emoji="", expiration=0)


def test_get_profile_status_null_status_fields():
    """Slack sometimes returns explicit None for cleared status fields."""
    c, _ = _client({"users.profile.get": {
        "ok": True,
        "profile": {
            "status_text": None,
            "status_emoji": None,
            "status_expiration": None,
        },
    }})
    _, status = c.get_profile_status()
    assert status == ProfileStatus(text="", emoji="", expiration=0)


def test_missing_scope_surfaces_needed():
    c, _ = _client({"users.profile.get": {
        "ok": False, "error": "missing_scope", "needed": "users.profile:read",
    }})
    health, status = c.get_profile_status()
    assert not health.ok
    assert health.error == "missing_scope"
    assert health.needed_scope == "users.profile:read"
    assert status is None


def test_transport_error_classified_as_network():
    c, _ = _client({"users.setPresence": {
        "ok": False, "_transport_error": "Connection refused",
    }})
    health = c.set_presence("auto")
    assert health.error == "network"
    assert health.detail == "Connection refused"


def test_rate_limited_with_retry_after():
    c, _ = _client({"users.setPresence": {
        "ok": False, "_http_status": 429, "_retry_after": 17,
    }})
    health = c.set_presence("away")
    assert health.error == "rate_limited"
    assert health.retry_after_seconds == 17


def test_rate_limited_without_retry_after_uses_default():
    c, _ = _client({"users.setPresence": {
        "ok": False, "_http_status": 429,
    }})
    health = c.set_presence("away")
    assert health.error == "rate_limited"
    assert health.retry_after_seconds == 30


def test_5xx_classified_as_server_error():
    c, _ = _client({"users.setPresence": {
        "ok": False, "_http_status": 502,
    }})
    health = c.set_presence("away")
    assert health.error == "server_error"
