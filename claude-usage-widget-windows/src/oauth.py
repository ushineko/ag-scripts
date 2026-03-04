"""OAuth credential management and Claude usage API client.

Reads OAuth tokens from ~/.claude/.credentials.json, auto-refreshes expired
access tokens, and fetches usage data from the Anthropic API. Implements
exponential backoff on refresh failures.

Ported from peripheral-battery-monitor with Windows path adjustments.
"""

import json
import os
import shutil
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import structlog

CLAUDE_CREDENTIALS_PATH = os.path.join(
    os.environ.get("USERPROFILE", os.path.expanduser("~")),
    ".claude", ".credentials.json",
)

CLAUDE_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
CLAUDE_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_TOKEN_URL = "https://console.anthropic.com/api/oauth/token"
CLAUDE_USER_AGENT = "claude-code/2.1.42"
CLAUDE_BETA_HEADER = "oauth-2025-04-20"

# OAuth refresh backoff state (in-memory, resets on app restart)
_oauth_backoff_until: float = 0.0
_oauth_fail_count: int = 0
_oauth_creds_mtime: float = 0.0

# Backoff constants (seconds)
_BACKOFF_TRANSIENT_BASE = 30
_BACKOFF_TRANSIENT_CAP = 300    # 5 minutes
_BACKOFF_PERMANENT_BASE = 60
_BACKOFF_PERMANENT_CAP = 1800   # 30 minutes


def reset_oauth_backoff() -> None:
    """Reset OAuth backoff state, allowing the next refresh attempt immediately."""
    global _oauth_backoff_until, _oauth_fail_count
    _oauth_backoff_until = 0.0
    _oauth_fail_count = 0


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


def _read_credentials() -> dict | None:
    """Read and return the Claude OAuth credentials, or None if unavailable."""
    try:
        with open(CLAUDE_CREDENTIALS_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return None


def _refresh_oauth_token(refresh_token: str) -> tuple[dict | None, bool]:
    """Refresh the OAuth access token.

    Returns:
        (token_data, is_permanent_error) — token_data is the parsed JSON on
        success or None on failure. is_permanent_error is True for HTTP 401/403.
    """
    log = structlog.get_logger()
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


def _save_credentials(creds: dict) -> None:
    """Write updated credentials back to disk."""
    try:
        with open(CLAUDE_CREDENTIALS_PATH, "w") as f:
            json.dump(creds, f)
    except OSError:
        pass


def _check_creds_mtime() -> None:
    """Check if credentials file changed on disk (e.g. after `claude login`). Reset backoff if so."""
    global _oauth_creds_mtime
    try:
        mtime = os.stat(CLAUDE_CREDENTIALS_PATH).st_mtime
    except OSError:
        return
    if mtime > _oauth_creds_mtime:
        if _oauth_creds_mtime > 0 and _oauth_fail_count > 0:
            log = structlog.get_logger()
            log.info("oauth_backoff_reset_creds_changed")
            reset_oauth_backoff()
        _oauth_creds_mtime = mtime


def _apply_backoff(is_permanent: bool) -> None:
    """Compute and set the next backoff deadline after a failed refresh."""
    global _oauth_backoff_until, _oauth_fail_count
    _oauth_fail_count += 1
    if is_permanent:
        delay = min(_BACKOFF_PERMANENT_BASE * (2 ** (_oauth_fail_count - 1)),
                     _BACKOFF_PERMANENT_CAP)
    else:
        delay = min(_BACKOFF_TRANSIENT_BASE * (2 ** (_oauth_fail_count - 1)),
                     _BACKOFF_TRANSIENT_CAP)
    _oauth_backoff_until = time.monotonic() + delay
    log = structlog.get_logger()
    log.warning("oauth_backoff_engaged", next_retry_secs=delay,
                fail_count=_oauth_fail_count,
                error_type="permanent" if is_permanent else "transient")


def fetch_claude_usage() -> dict | None:
    """Fetch Claude Code usage from the Anthropic OAuth API.

    Reads the OAuth token from ~/.claude/.credentials.json, refreshes if
    expired, and calls GET /api/oauth/usage. Returns the parsed JSON response
    or None on error. Applies exponential backoff on repeated refresh failures.
    """
    global _oauth_backoff_until, _oauth_fail_count
    log = structlog.get_logger()

    _check_creds_mtime()

    creds = _read_credentials()
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

        if time.monotonic() < _oauth_backoff_until:
            log.debug("oauth_refresh_skipped_backoff", fail_count=_oauth_fail_count)
            return {"error": "auth_backoff"}

        new_token_data, is_permanent = _refresh_oauth_token(refresh_token)
        if not new_token_data or "access_token" not in new_token_data:
            _apply_backoff(is_permanent)
            return {"error": "auth_expired"}

        # Success — reset backoff
        _oauth_fail_count = 0
        _oauth_backoff_until = 0.0

        access_token = new_token_data["access_token"]
        oauth["accessToken"] = access_token
        if "refresh_token" in new_token_data:
            oauth["refreshToken"] = new_token_data["refresh_token"]
        if "expires_in" in new_token_data:
            oauth["expiresAt"] = now_ms + new_token_data["expires_in"] * 1000
        _save_credentials(creds)

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
        log.warning("claude_usage_api_error", status=e.code)
        return {"error": "api_error"}
    except (urllib.error.URLError, TimeoutError) as e:
        log.warning("claude_usage_network_error", error=str(e))
        return {"error": "offline"}
    except json.JSONDecodeError:
        log.warning("claude_usage_invalid_json")
        return {"error": "invalid_response"}
