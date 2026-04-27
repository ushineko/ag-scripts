from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Literal

log = logging.getLogger(__name__)

SLACK_API = "https://slack.com/api"

Transport = Callable[[str, dict, bool], dict]
"""HTTP transport for tests. Args: (method, params, json_body). Returns parsed JSON."""


@dataclass(frozen=True)
class ApiHealth:
    ok: bool
    error: str | None = None
    needed_scope: str | None = None
    retry_after_seconds: int | None = None
    detail: str | None = None

    @classmethod
    def success(cls) -> ApiHealth:
        return cls(ok=True)


@dataclass(frozen=True)
class AuthInfo:
    user: str
    team: str
    user_id: str
    team_id: str


@dataclass(frozen=True)
class PresenceState:
    presence: str
    online: bool
    auto_away: bool
    manual_away: bool
    connection_count: int
    last_activity: int


@dataclass(frozen=True)
class ProfileStatus:
    text: str
    emoji: str
    expiration: int


class SlackClient:
    """Thin wrapper around the Slack web API methods this app uses.

    Methods return ApiHealth (always) plus parsed result data when applicable.
    Tests inject a custom transport; production uses urllib.
    """

    def __init__(
        self,
        token: str,
        *,
        base_url: str = SLACK_API,
        timeout: float = 10.0,
        transport: Transport | None = None,
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport or self._default_transport

    def auth_test(self) -> tuple[ApiHealth, AuthInfo | None]:
        resp = self._call("auth.test", {})
        health = _parse_health(resp)
        if not health.ok:
            return health, None
        return health, AuthInfo(
            user=resp.get("user", ""),
            team=resp.get("team", ""),
            user_id=resp.get("user_id", ""),
            team_id=resp.get("team_id", ""),
        )

    def get_presence(self) -> tuple[ApiHealth, PresenceState | None]:
        resp = self._call("users.getPresence", {})
        health = _parse_health(resp)
        if not health.ok:
            return health, None
        return health, PresenceState(
            presence=resp.get("presence", ""),
            online=bool(resp.get("online", False)),
            auto_away=bool(resp.get("auto_away", False)),
            manual_away=bool(resp.get("manual_away", False)),
            connection_count=int(resp.get("connection_count", 0)),
            last_activity=int(resp.get("last_activity", 0)),
        )

    def set_presence(self, presence: Literal["auto", "away"]) -> ApiHealth:
        if presence not in ("auto", "away"):
            raise ValueError(f"presence must be 'auto' or 'away', got {presence!r}")
        resp = self._call("users.setPresence", {"presence": presence})
        return _parse_health(resp)

    def get_profile_status(self) -> tuple[ApiHealth, ProfileStatus | None]:
        resp = self._call("users.profile.get", {})
        health = _parse_health(resp)
        if not health.ok:
            return health, None
        profile = resp.get("profile") or {}
        return health, ProfileStatus(
            text=str(profile.get("status_text") or ""),
            emoji=str(profile.get("status_emoji") or ""),
            expiration=int(profile.get("status_expiration") or 0),
        )

    def set_profile_status(self, text: str, emoji: str, expiration: int) -> ApiHealth:
        body = {
            "profile": {
                "status_text": text,
                "status_emoji": emoji,
                "status_expiration": int(expiration),
            }
        }
        resp = self._call("users.profile.set", body, json_body=True)
        return _parse_health(resp)

    def _call(self, method: str, params: dict, json_body: bool = False) -> dict:
        return self._transport(method, params, json_body)

    def _default_transport(self, method: str, params: dict, json_body: bool) -> dict:
        url = f"{self._base_url}/{method}"
        headers = {"Authorization": f"Bearer {self._token}"}
        if json_body:
            data = json.dumps(params).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        else:
            data = urllib.parse.urlencode(params).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        req = urllib.request.Request(url, data=data, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = resp.read()
                return json.loads(body.decode("utf-8"))
        except urllib.error.HTTPError as e:
            retry_after = e.headers.get("Retry-After") if e.headers else None
            payload: dict = {
                "ok": False,
                "_http_status": e.code,
            }
            if retry_after:
                try:
                    payload["_retry_after"] = int(retry_after)
                except ValueError:
                    pass
            try:
                payload.update(json.loads(e.read().decode("utf-8")))
            except (ValueError, UnicodeDecodeError):
                pass
            return payload
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            return {"ok": False, "_transport_error": str(e)}


def _parse_health(resp: dict) -> ApiHealth:
    if resp.get("ok"):
        return ApiHealth.success()

    error = resp.get("error")
    needed_scope = resp.get("needed") if error == "missing_scope" else None
    detail = resp.get("_transport_error")

    retry_after = resp.get("_retry_after")
    if retry_after is None and resp.get("_http_status") == 429:
        retry_after = 30  # conservative default if no header

    if not error and detail:
        error = "network"
    elif not error and resp.get("_http_status"):
        status = resp["_http_status"]
        if 500 <= status <= 599:
            error = "server_error"
        elif status == 429:
            error = "rate_limited"
        else:
            error = f"http_{status}"

    return ApiHealth(
        ok=False,
        error=error,
        needed_scope=needed_scope,
        retry_after_seconds=retry_after,
        detail=detail,
    )
