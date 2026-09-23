"""Codex app-server response handling and normalization."""

import json
import queue
import time
from pathlib import Path
from unittest import mock

from src import codex_usage


def test_find_codex_prefers_explicit_override(monkeypatch):
    monkeypatch.setenv("CODEX_PATH", "/custom/bin/codex")
    monkeypatch.setattr(codex_usage.shutil, "which",
                        lambda name: name if name == "/custom/bin/codex" else None)

    assert codex_usage.find_codex_executable() == "/custom/bin/codex"


def test_find_codex_uses_path(monkeypatch):
    monkeypatch.delenv("CODEX_PATH", raising=False)
    monkeypatch.setattr(codex_usage.shutil, "which",
                        lambda name: "/path/bin/codex" if name == "codex" else None)

    assert codex_usage.find_codex_executable() == "/path/bin/codex"


def test_find_codex_checks_miniforge_when_path_is_restricted(tmp_path, monkeypatch):
    executable = tmp_path / "miniforge3" / "bin" / "codex"
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o755)
    monkeypatch.delenv("CODEX_PATH", raising=False)
    monkeypatch.setattr(codex_usage.shutil, "which", lambda _name: None)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    assert codex_usage.find_codex_executable() == str(executable)


def test_find_codex_returns_none_when_unavailable(tmp_path, monkeypatch):
    monkeypatch.delenv("CODEX_PATH", raising=False)
    monkeypatch.setattr(codex_usage.shutil, "which", lambda _name: None)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    with mock.patch.object(codex_usage.os, "access", return_value=False):
        assert codex_usage.find_codex_executable() is None


def test_wait_for_id_ignores_notifications_and_unrelated_responses():
    output = queue.Queue()
    output.put(json.dumps({"jsonrpc": "2.0", "method": "account/updated"}))
    output.put(json.dumps({"jsonrpc": "2.0", "id": 99, "result": {}}))
    output.put(json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"ok": True}}))

    response = codex_usage._wait_for_id(output, 2, time.monotonic() + 1)

    assert response["result"] == {"ok": True}


def test_normalize_business_limits_without_exposing_account_ids():
    result = {
        "accountId": "must-not-be-cached",
        "planType": "self_serve_business_prolite",
        "rateLimitsByLimitId": {
            "codex": {
                "primary": {
                    "usedPercent": 2,
                    "windowDurationMins": 10080,
                    "resetsAt": 1800000000,
                },
                "secondary": None,
                "planType": "self_serve_business_prolite",
                "individualLimit": {
                    "limit": "1200",
                    "used": "403.5",
                    "remainingPercent": 66,
                    "resetsAt": 1801000000,
                },
                "credits": {"hasCredits": True, "unlimited": False,
                            "balance": None},
            }
        },
    }

    data = codex_usage.normalize_rate_limits(result)

    assert data["primary"] == {
        "utilization": 2.0,
        "window_minutes": 10080,
        "resets_at": 1800000000,
    }
    assert data["individual_limit"]["utilization"] == 34.0
    assert data["individual_limit"]["used"] == "403.5"
    assert "accountId" not in data
    assert "must-not-be-cached" not in json.dumps(data)


def test_normalize_falls_back_to_aggregate_rate_limits():
    data = codex_usage.normalize_rate_limits({
        "rateLimits": {
            "primary": {"usedPercent": 51, "windowDurationMins": 300},
            "secondary": {"usedPercent": 9, "windowDurationMins": 10080},
        }
    })

    assert data["primary"]["utilization"] == 51
    assert data["secondary"]["window_minutes"] == 10080
