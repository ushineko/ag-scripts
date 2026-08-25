"""Pure display logic — no Qt dependency.

Color thresholds, formatting functions, and error message mapping used by
both the widget and tray modules, and testable without PySide6 installed.
"""

from __future__ import annotations

# Color hex values
COLOR_GREEN = "#4caf50"
COLOR_YELLOW = "#ff9800"
COLOR_RED = "#f44336"
COLOR_GRAY = "#6b7280"


def usage_color(utilization: float | None) -> str:
    """Return hex color for a utilization percentage (0-100)."""
    if utilization is None:
        return COLOR_GRAY
    if utilization > 80:
        return COLOR_RED
    if utilization >= 50:
        return COLOR_YELLOW
    return COLOR_GREEN


def severity_color(severity: str | None, percent: float | None = None) -> str:
    """Return hex color for a ``spend.severity`` value.

    The credits shape reports its own severity, so honor that rather than
    re-deriving a threshold from percent — the API decides what counts as
    concerning. ``percent`` is only a fallback for an unrecognized severity.
    """
    mapping = {
        "normal": COLOR_GREEN,
        "warning": COLOR_YELLOW,
        "elevated": COLOR_YELLOW,
        "critical": COLOR_RED,
        "exceeded": COLOR_RED,
    }
    if severity in mapping:
        return mapping[severity]
    return usage_color(percent)


def format_percentage(utilization: float | None) -> str:
    """Format utilization percentage (0-100) as a display string."""
    if utilization is None:
        return "--"
    return f"{utilization:.0f}%"


def error_message(error_code: str) -> str:
    """Map error codes to user-facing messages."""
    messages = {
        "auth_expired": "Auth expired \u2014 run `claude login`",
        "auth_backoff": "(stale \u2014 retrying...)",
        "rate_limited": "(rate limited \u2014 backing off)",
        "api_error": "(API error)",
        "offline": "(offline)",
        "invalid_response": "(invalid API response)",
    }
    return messages.get(error_code, f"Error: {error_code}")
