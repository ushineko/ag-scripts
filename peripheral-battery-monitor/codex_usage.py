"""Codex rate-limit client backed by the supported app-server JSON-RPC API."""

from __future__ import annotations

import json
import queue
import shutil
import subprocess
import threading
import time
from typing import Any

import structlog

log = structlog.get_logger(__name__)

_INITIALIZE_ID = 1
_RATE_LIMITS_ID = 2


def is_codex_installed() -> bool:
    return shutil.which("codex") is not None


def _reader(stream, output: queue.Queue) -> None:
    try:
        for line in iter(stream.readline, ""):
            output.put(line)
    finally:
        output.put(None)


def _send(proc: subprocess.Popen, message: dict) -> None:
    proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.flush()


def _wait_for_id(output: queue.Queue, request_id: int, deadline: float) -> dict:
    """Return the matching response, ignoring notifications and other IDs."""
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        try:
            line = output.get(timeout=remaining)
        except queue.Empty as exc:
            raise TimeoutError from exc
        if line is None:
            raise RuntimeError("app-server closed its output")
        try:
            message = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(message, dict) and message.get("id") == request_id:
            return message


def _percent(value: Any) -> float | None:
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return None


def _window(value: Any) -> dict | None:
    if not isinstance(value, dict):
        return None
    utilization = _percent(value.get("usedPercent"))
    duration = value.get("windowDurationMins")
    resets_at = value.get("resetsAt")
    if utilization is None and duration is None and resets_at is None:
        return None
    return {
        "utilization": utilization,
        "window_minutes": duration if isinstance(duration, (int, float)) else None,
        "resets_at": resets_at if isinstance(resets_at, (int, float)) else None,
    }


def normalize_rate_limits(result: dict) -> dict:
    """Reduce the app-server response to display data and omit account IDs."""
    limits_by_id = result.get("rateLimitsByLimitId") or {}
    limits = limits_by_id.get("codex") if isinstance(limits_by_id, dict) else None
    if not isinstance(limits, dict):
        limits = result.get("rateLimits") or {}

    normalized = {
        "provider": "codex",
        "primary": _window(limits.get("primary")),
        "secondary": _window(limits.get("secondary")),
        "plan_type": limits.get("planType") or result.get("planType"),
        "credits": limits.get("credits")
        if isinstance(limits.get("credits"), dict) else None,
        "rate_limit_reached_type": limits.get("rateLimitReachedType"),
    }

    individual = limits.get("individualLimit")
    if isinstance(individual, dict):
        remaining = _percent(individual.get("remainingPercent"))
        normalized["individual_limit"] = {
            "utilization": None if remaining is None else 100.0 - remaining,
            "remaining_percent": remaining,
            "resets_at": individual.get("resetsAt"),
            "used": individual.get("used"),
            "limit": individual.get("limit"),
        }
    else:
        normalized["individual_limit"] = None
    return normalized


def fetch_codex_usage(_store_dir=None, timeout: float = 12.0) -> dict | None:
    """Fetch and normalize Codex usage, returning a compact error on failure."""
    if not is_codex_installed():
        return None
    proc = None
    try:
        proc = subprocess.Popen(
            ["codex", "app-server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        output: queue.Queue = queue.Queue()
        threading.Thread(target=_reader, args=(proc.stdout, output), daemon=True).start()
        deadline = time.monotonic() + timeout
        _send(proc, {
            "jsonrpc": "2.0", "id": _INITIALIZE_ID, "method": "initialize",
            "params": {"clientInfo": {"name": "usage-monitor", "version": "1"}},
        })
        initialized = _wait_for_id(output, _INITIALIZE_ID, deadline)
        if "error" in initialized:
            return {"provider": "codex", "error": "api_error"}
        _send(proc, {"jsonrpc": "2.0", "method": "initialized", "params": {}})
        _send(proc, {
            "jsonrpc": "2.0", "id": _RATE_LIMITS_ID,
            "method": "account/rateLimits/read",
            "params": {"excludeResetCreditDetails": True},
        })
        response = _wait_for_id(output, _RATE_LIMITS_ID, deadline)
        if "error" in response:
            error = response.get("error") or {}
            text = str(error.get("message", "")).lower()
            code = "not_logged_in" if "login" in text or "auth" in text else "api_error"
            return {"provider": "codex", "error": code}
        result = response.get("result")
        if not isinstance(result, dict):
            return {"provider": "codex", "error": "invalid_response"}
        return normalize_rate_limits(result)
    except FileNotFoundError:
        return None
    except TimeoutError:
        log.warning("codex_usage_timeout")
        return {"provider": "codex", "error": "timeout"}
    except (OSError, RuntimeError, BrokenPipeError) as exc:
        log.warning("codex_usage_failed", error=str(exc))
        return {"provider": "codex", "error": "offline"}
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=1)
