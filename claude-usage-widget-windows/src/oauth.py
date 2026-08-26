"""OAuth credential management and Claude usage API client.

Reads OAuth tokens from the platform credential store (macOS login Keychain;
~/.claude/.credentials.json on Windows/Linux), auto-refreshes expired access
tokens, and fetches usage data from the Anthropic API. Implements exponential
backoff on refresh failures.

Ported from peripheral-battery-monitor with Windows path adjustments.
"""

from __future__ import annotations

import getpass
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import structlog

from .platform_support import IS_MACOS

CLAUDE_CREDENTIALS_PATH = os.path.join(
    os.environ.get("USERPROFILE", os.path.expanduser("~")),
    ".claude", ".credentials.json",
)

# On macOS, Claude Code stores OAuth credentials in the login Keychain as a
# generic password (service name below, account = the macOS username) rather
# than in ~/.claude/.credentials.json. We read/write the Keychain via the
# `security` CLI on macOS and fall back to the file path elsewhere.
KEYCHAIN_SERVICE = "Claude Code-credentials"

CLAUDE_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
CLAUDE_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_TOKEN_URL = "https://console.anthropic.com/api/oauth/token"
CLAUDE_USER_AGENT = "claude-code/2.1.42"
CLAUDE_BETA_HEADER = "oauth-2025-04-20"

# Backoff constants (seconds)
_BACKOFF_TRANSIENT_BASE = 30
_BACKOFF_TRANSIENT_CAP = 300    # 5 minutes
_BACKOFF_PERMANENT_BASE = 60
_BACKOFF_PERMANENT_CAP = 1800   # 30 minutes


class _AccountState:
    """In-memory OAuth refresh state for one credential store.

    Spec 011: state is per store, not per process. One account in permanent
    backoff (revoked seat, expired refresh token) must not suppress refresh
    attempts for another account that is perfectly healthy.
    """

    __slots__ = ("backoff_until", "fail_count", "creds_mtime")

    def __init__(self) -> None:
        self.backoff_until: float = 0.0
        self.fail_count: int = 0
        self.creds_mtime: float = 0.0


# Keyed by credential-store directory. Resets on app restart.
_states: dict[str, _AccountState] = {}


def default_store_dir() -> str:
    """Directory of the default credential store (``~/.claude``)."""
    return os.path.dirname(CLAUDE_CREDENTIALS_PATH)


def _state(store_dir: str | None) -> _AccountState:
    """Return the backoff state for a store, creating it on first use."""
    key = store_dir or default_store_dir()
    state = _states.get(key)
    if state is None:
        state = _AccountState()
        _states[key] = state
    return state


def reset_oauth_backoff(store_dir: str | None = None) -> None:
    """Reset OAuth backoff state, allowing the next refresh attempt immediately.

    With no argument, resets every known account — matching the previous
    single-account behavior for callers that just want a clean slate.
    """
    if store_dir is None:
        for state in _states.values():
            state.backoff_until = 0.0
            state.fail_count = 0
        return
    state = _state(store_dir)
    state.backoff_until = 0.0
    state.fail_count = 0


def is_in_backoff(store_dir: str | None = None) -> bool:
    """True when this store (or any store, with no argument) is backing off."""
    if store_dir is None:
        return any(
            s.fail_count > 0 and time.monotonic() < s.backoff_until
            for s in _states.values()
        )
    state = _state(store_dir)
    return state.fail_count > 0 and time.monotonic() < state.backoff_until


def is_claude_installed() -> bool:
    """Check if Claude Code CLI is installed on the system."""
    return shutil.which("claude") is not None


def get_time_until_reset(resets_at: str) -> str:
    """Calculate human-readable time remaining until reset from an ISO 8601 timestamp."""
    now = datetime.now(timezone.utc)
    try:
        reset_time = datetime.fromisoformat(resets_at)
    except (ValueError, TypeError):
        return "Unknown"

    delta = reset_time - now
    if delta.total_seconds() <= 0:
        return "Resetting..."

    hours = int(delta.total_seconds() // 3600)
    minutes = int((delta.total_seconds() % 3600) // 60)

    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _credentials_path(store_dir: str | None) -> str:
    """Path to the credentials file for a store, or the default store's."""
    if store_dir is None:
        return CLAUDE_CREDENTIALS_PATH
    return os.path.join(store_dir, ".credentials.json")


def _read_credentials_file(store_dir: str | None = None) -> dict | None:
    """Read Claude OAuth credentials from a store's .credentials.json."""
    try:
        with open(_credentials_path(store_dir), "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return None


def _read_credentials_keychain() -> dict | None:
    """Read Claude OAuth credentials from the macOS login Keychain."""
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    raw = result.stdout.strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _read_credentials(store_dir: str | None = None) -> dict | None:
    """Read and return the Claude OAuth credentials, or None if unavailable.

    On macOS the *default* store lives in the login Keychain rather than on
    disk. Non-default profile stores are always files: Claude Code namespaces
    the Keychain item by a hash of the store directory, which is not
    reproducible from here, so a named profile is read from its file.
    """
    if IS_MACOS and store_dir is None:
        return _read_credentials_keychain()
    return _read_credentials_file(store_dir)


def _refresh_oauth_token(
    refresh_token: str, fail_count: int = 0
) -> tuple[dict | None, bool]:
    """Refresh the OAuth access token.

    ``fail_count`` is this store's consecutive-failure count, used only to
    decide log level so a persistently broken account does not spam warnings.

    Returns:
        (token_data, is_permanent_error) — token_data is the parsed JSON on
        success or None on failure. is_permanent_error is True for HTTP 401/403.
    """
    log = structlog.get_logger()
    _oauth_fail_count = fail_count
    body = json.dumps({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLAUDE_OAUTH_CLIENT_ID,
    }).encode()

    req = urllib.request.Request(
        CLAUDE_TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()), False
    except urllib.error.HTTPError as e:
        is_permanent = e.code in (401, 403)
        if _oauth_fail_count == 0:
            log.warning("oauth_refresh_failed", error=str(e), status=e.code)
        else:
            log.debug("oauth_refresh_failed", error=str(e), status=e.code,
                       fail_count=_oauth_fail_count)
        return None, is_permanent
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        if _oauth_fail_count == 0:
            log.warning("oauth_refresh_failed", error=str(e))
        else:
            log.debug("oauth_refresh_failed", error=str(e),
                       fail_count=_oauth_fail_count)
        return None, False


def _save_credentials_file(creds: dict, store_dir: str | None = None) -> None:
    """Write updated credentials back to the store they came from.

    Writing to the originating store matters with more than one account: a
    refreshed token written to the default store would overwrite an unrelated
    account's credentials.
    """
    path = _credentials_path(store_dir)
    try:
        with open(path, "w") as f:
            json.dump(creds, f)
        # Assert 0600 rather than inheriting whatever the file/umask had.
        os.chmod(path, 0o600)
    except OSError:
        pass


def _save_credentials_keychain(creds: dict) -> None:
    """Write updated credentials back to the macOS login Keychain.

    Uses ``-U`` to update the existing generic-password item in place. The
    account is the current macOS username, matching how Claude Code stores it.
    """
    account = os.environ.get("USER") or getpass.getuser()
    try:
        subprocess.run(
            ["security", "add-generic-password", "-U",
             "-s", KEYCHAIN_SERVICE, "-a", account, "-w", json.dumps(creds)],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def _save_credentials(creds: dict, store_dir: str | None = None) -> None:
    """Write updated credentials back to the platform credential store."""
    if IS_MACOS and store_dir is None:
        _save_credentials_keychain(creds)
    else:
        _save_credentials_file(creds, store_dir)


def _keychain_mtime() -> float:
    """Modification time (epoch seconds) of the Keychain creds item, or 0.0.

    Parses the ``"mdat"<timedate>=... "YYYYMMDDhhmmssZ"`` field from
    ``security``'s attribute dump. Returns 0.0 if unavailable/unparseable, in
    which case the change-watch simply doesn't fire (manual Refresh still works).
    """
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return 0.0
    if result.returncode != 0:
        return 0.0
    match = re.search(r'"mdat".*?"(\d{14})Z', result.stdout)
    if not match:
        return 0.0
    try:
        dt = datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return 0.0


def _creds_mtime(store_dir: str | None = None) -> float:
    """Modification time of a credential store, or 0.0 if unknown."""
    if IS_MACOS and store_dir is None:
        return _keychain_mtime()
    try:
        return os.stat(_credentials_path(store_dir)).st_mtime
    except OSError:
        return 0.0


def _check_creds_mtime(store_dir: str | None = None) -> None:
    """Reset this store's backoff if it changed (e.g. after `claude login`)."""
    state = _state(store_dir)
    mtime = _creds_mtime(store_dir)
    if mtime <= 0:
        return
    if mtime > state.creds_mtime:
        if state.creds_mtime > 0 and state.fail_count > 0:
            log = structlog.get_logger()
            log.info("oauth_backoff_reset_creds_changed", store=store_dir)
            reset_oauth_backoff(store_dir)
        state.creds_mtime = mtime


def _apply_backoff(is_permanent: bool, store_dir: str | None = None) -> None:
    """Compute and set the next backoff deadline after a failed refresh."""
    state = _state(store_dir)
    state.fail_count += 1
    if is_permanent:
        delay = min(_BACKOFF_PERMANENT_BASE * (2 ** (state.fail_count - 1)),
                     _BACKOFF_PERMANENT_CAP)
    else:
        delay = min(_BACKOFF_TRANSIENT_BASE * (2 ** (state.fail_count - 1)),
                     _BACKOFF_TRANSIENT_CAP)
    state.backoff_until = time.monotonic() + delay
    log = structlog.get_logger()
    log.warning("oauth_backoff_engaged", next_retry_secs=delay,
                fail_count=state.fail_count, store=store_dir,
                error_type="permanent" if is_permanent else "transient")


def fetch_claude_usage(store_dir: str | None = None) -> dict | None:
    """Fetch Claude Code usage from the Anthropic OAuth API.

    Reads the OAuth token from ``store_dir`` (the default store when None),
    refreshes if expired, and calls GET /api/oauth/usage. Returns the parsed
    JSON response or None on error. Applies exponential backoff, per store, on
    repeated refresh failures.
    """
    log = structlog.get_logger()
    state = _state(store_dir)

    _check_creds_mtime(store_dir)

    creds = _read_credentials(store_dir)
    if not creds:
        return None

    oauth = creds.get("claudeAiOauth")
    if not oauth:
        return None

    access_token = oauth.get("accessToken")
    refresh_token = oauth.get("refreshToken")
    expires_at = oauth.get("expiresAt", 0)

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if now_ms >= expires_at:
        if not refresh_token:
            log.warning("claude_token_expired_no_refresh")
            return {"error": "auth_expired"}

        if time.monotonic() < state.backoff_until:
            log.debug("oauth_refresh_skipped_backoff",
                      fail_count=state.fail_count, store=store_dir)
            return {"error": "auth_backoff"}

        new_token_data, is_permanent = _refresh_oauth_token(
            refresh_token, state.fail_count
        )
        if not new_token_data or "access_token" not in new_token_data:
            _apply_backoff(is_permanent, store_dir)
            return {"error": "auth_expired"}

        # Success — reset this store's backoff
        state.fail_count = 0
        state.backoff_until = 0.0

        access_token = new_token_data["access_token"]
        oauth["accessToken"] = access_token
        if "refresh_token" in new_token_data:
            oauth["refreshToken"] = new_token_data["refresh_token"]
        if "expires_in" in new_token_data:
            oauth["expiresAt"] = now_ms + new_token_data["expires_in"] * 1000
        _save_credentials(creds, store_dir)

    req = urllib.request.Request(
        CLAUDE_USAGE_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": CLAUDE_USER_AGENT,
            "anthropic-beta": CLAUDE_BETA_HEADER,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            retry_after = _parse_retry_after(e)
            log.warning("claude_usage_rate_limited", status=429, retry_after=retry_after)
            return {"error": "rate_limited", "retry_after": retry_after}
        log.warning("claude_usage_api_error", status=e.code)
        return {"error": "api_error"}
    except (urllib.error.URLError, TimeoutError) as e:
        log.warning("claude_usage_network_error", error=str(e))
        return {"error": "offline"}
    except json.JSONDecodeError:
        log.warning("claude_usage_invalid_json")
        return {"error": "invalid_response"}


def _parse_retry_after(e: urllib.error.HTTPError) -> int | None:
    """Return the Retry-After header as integer seconds, or None.

    Only the delta-seconds form is parsed; the HTTP-date form falls back to
    None (the caller applies its own backoff in that case).
    """
    try:
        value = e.headers.get("Retry-After")
    except AttributeError:
        return None
    if not value:
        return None
    try:
        seconds = int(value.strip())
    except (ValueError, AttributeError):
        return None
    return seconds if seconds >= 0 else None
