"""Account-shape detection for the ``/api/oauth/usage`` payload.

Personal accounts report per-user rate-limit windows (``five_hour``,
``seven_day``, ...). Org-provisioned enterprise seats do not: every rate-limit
bucket comes back ``null`` and the only live figures are the member's own
overage spend (``spend`` / ``extra_usage``) against a monthly credit cap.

Detection is by **data presence**, not by account type. The API does not report
account type directly, and the bucket names visibly rotate (``tangelo``,
``nimbus_quill``, ``cinder_cove``, ...), so keying on what is actually populated
survives a rename where keying on identity would not.

This module is deliberately dependency-free — no Qt, no I/O, no network — so it
is unit-testable in isolation and can be copied verbatim into
``peripheral-battery-monitor`` (see spec 015 there).
"""

from __future__ import annotations

from datetime import datetime

import structlog

log = structlog.get_logger(__name__)

# Shapes returned by detect_shape().
SHAPE_LIMITS = "limits"
SHAPE_CREDITS = "credits"
SHAPE_UNAVAILABLE = "unavailable"

# Keys that are never rate-limit buckets, so live_buckets() must skip them.
_NON_BUCKET_KEYS = frozenset(
    {"extra_usage", "spend", "limits", "member_dashboard_available", "error"}
)

# Buckets rendered first when present, in this order. Anything else that passes
# bucket_is_live() is still reported by live_buckets(), just not prioritized.
PRIMARY_BUCKETS = ("five_hour", "seven_day")


def bucket_is_live(bucket: object) -> bool:
    """Return True when ``bucket`` is a rate-limit window with real data.

    A bucket qualifies when it is a dict, carries a non-null ``utilization``,
    and either has a ``resets_at`` or reports non-zero usage.

    The ``resets_at`` clause is what rejects the enterprise placeholder
    (``nimbus_quill``: ``utilization`` 0.0 with every other field null) — a real
    rate-limit window always carries a reset timestamp. The ``utilization > 0``
    escape hatch avoids hiding a genuinely live bucket that omits its reset time.
    """
    if not isinstance(bucket, dict):
        return False
    utilization = bucket.get("utilization")
    if utilization is None:
        return False
    return bucket.get("resets_at") is not None or utilization > 0


def live_buckets(data: dict) -> dict[str, dict]:
    """Return the live rate-limit buckets in ``data``, keyed by name.

    Non-null buckets rejected by :func:`bucket_is_live` are logged at debug
    level so a future shape change is diagnosable from logs rather than from a
    crash.
    """
    if not isinstance(data, dict):
        return {}

    live: dict[str, dict] = {}
    for key, value in data.items():
        if key in _NON_BUCKET_KEYS or value is None:
            continue
        if bucket_is_live(value):
            live[key] = value
        elif isinstance(value, dict):
            # Log only the two fields the heuristic reads, not the whole dict —
            # enough to diagnose a shape change without dumping unknown future
            # fields into the log.
            log.debug(
                "usage_bucket_rejected",
                bucket=key,
                utilization=value.get("utilization"),
                resets_at=value.get("resets_at"),
            )
    return live


def detect_shape(data: dict) -> str:
    """Classify a usage payload as ``limits``, ``credits`` or ``unavailable``.

    Resolution is ordered: live rate-limit buckets win when present, matching
    what Claude Code's own ``/usage`` screen displays.
    """
    if not isinstance(data, dict):
        return SHAPE_UNAVAILABLE
    if live_buckets(data):
        return SHAPE_LIMITS
    if credits_view(data) is not None:
        return SHAPE_CREDITS
    return SHAPE_UNAVAILABLE


def _minor_to_major(amount: dict | None) -> float | None:
    """Convert an ``{amount_minor, exponent}`` money object to a float."""
    if not isinstance(amount, dict):
        return None
    minor = amount.get("amount_minor")
    if minor is None:
        return None
    exponent = amount.get("exponent") or 0
    return minor / (10**exponent)


def credits_view(data: dict) -> dict | None:
    """Return a normalized credits reading, or None when unavailable.

    Reads ``spend`` rather than ``extra_usage``. Both carry identical numbers,
    but ``spend`` exposes ``severity`` (which maps onto ``usage_color``) and
    handles currency via explicit ``amount_minor`` + ``exponent`` instead of
    requiring reassembly from ``used_credits`` + ``decimal_places``.
    """
    if not isinstance(data, dict):
        return None
    spend = data.get("spend")
    if not isinstance(spend, dict) or not spend.get("enabled"):
        return None

    used = _minor_to_major(spend.get("used"))
    limit = _minor_to_major(spend.get("limit"))
    if used is None or limit is None:
        return None

    currency = (spend.get("used") or {}).get("currency") or "USD"
    return {
        "used": used,
        "limit": limit,
        "percent": spend.get("percent"),
        "severity": spend.get("severity") or "normal",
        "currency": currency,
        # Derived, not from the API — the payload carries no reset field for the
        # credit cap. Claude Code's /usage computes first-of-next-month locally.
        "resets_at": next_month_reset(),
    }


def next_month_reset(now: datetime | None = None) -> datetime:
    """First instant of next month, in local time.

    Derived value: the usage payload has no reset field for the monthly credit
    cap, so this reproduces what Claude Code's ``/usage`` screen displays
    (e.g. "Resets Sep 1").
    """
    now = now or datetime.now()
    if now.month == 12:
        return now.replace(
            year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    return now.replace(
        month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0
    )


def format_credits(view: dict) -> str:
    """Compact credits string, e.g. ``$2.79 / $200.00 (1%)``."""
    symbol = "$" if view.get("currency") == "USD" else ""
    percent = view.get("percent")
    text = f"{symbol}{view['used']:.2f} / {symbol}{view['limit']:.2f}"
    if percent is not None:
        text += f" ({percent:.0f}%)"
    return text
