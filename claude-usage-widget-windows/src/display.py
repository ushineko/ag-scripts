"""Pure display logic — no Qt dependency.

Color thresholds, formatting functions, and error message mapping used by
both the widget and tray modules, and testable without PySide6 installed.
"""

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
        "api_error": "(API error)",
        "offline": "(offline)",
        "invalid_response": "(invalid API response)",
    }
    return messages.get(error_code, f"Error: {error_code}")
