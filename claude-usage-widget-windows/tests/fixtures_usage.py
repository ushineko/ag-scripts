"""Captured ``/api/oauth/usage`` payloads for the two account shapes.

ENTERPRISE_PAYLOAD is a real response from an org-provisioned seat, captured
2026-08-25 (dollar figures preserved, no credentials present). Every rate-limit
bucket is null; ``nimbus_quill`` is the empty placeholder that must not be
mistaken for a live bucket.

PERSONAL_PAYLOAD mirrors the shape a personal subscription returns, matching the
values already asserted in the peripheral-battery-monitor suite.
"""

ENTERPRISE_PAYLOAD = {
    "five_hour": None,
    "seven_day": None,
    "seven_day_oauth_apps": None,
    "seven_day_opus": None,
    "seven_day_sonnet": None,
    "seven_day_cowork": None,
    "seven_day_omelette": None,
    "tangelo": None,
    "iguana_necktie": None,
    "omelette_promotional": None,
    "nimbus_quill": {
        "utilization": 0.0,
        "resets_at": None,
        "limit_dollars": None,
        "used_dollars": None,
        "remaining_dollars": None,
    },
    "cinder_cove": None,
    "amber_ladder": None,
    "extra_usage": {
        "is_enabled": True,
        "monthly_limit": 20000,
        "used_credits": 279.0,
        "utilization": 1.395,
        "currency": "USD",
        "decimal_places": 2,
        "disabled_reason": None,
        "user_disabled": False,
        "spend_limit_reached": False,
        "credits_ever_enabled": True,
        "daily": None,
        "weekly": None,
    },
    "limits": [],
    "spend": {
        "used": {"amount_minor": 279, "currency": "USD", "exponent": 2},
        "limit": {"amount_minor": 20000, "currency": "USD", "exponent": 2},
        "percent": 1,
        "severity": "normal",
        "enabled": True,
        "disabled_reason": None,
        "cap": {"money": None, "credits": {"amount_minor": 20000, "exponent": 2}},
        "balance": None,
        "auto_reload": None,
        "disclaimer": "Usage credits cover you when you hit your plan limits.",
        "can_purchase_credits": False,
        "can_toggle": False,
    },
    "member_dashboard_available": True,
}

PERSONAL_PAYLOAD = {
    "five_hour": {"utilization": 70.0, "resets_at": "2026-02-16T22:00:00+00:00"},
    "seven_day": {"utilization": 25.0, "resets_at": "2026-02-21T00:00:00+00:00"},
    "seven_day_opus": {"utilization": 12.0, "resets_at": "2026-02-21T00:00:00+00:00"},
    "seven_day_sonnet": None,
    "extra_usage": None,
    "spend": None,
    "limits": [],
    "member_dashboard_available": False,
}

# Neither buckets nor spend — e.g. spend disabled on an account with no windows.
UNAVAILABLE_PAYLOAD = {
    "five_hour": None,
    "seven_day": None,
    "nimbus_quill": {"utilization": 0.0, "resets_at": None},
    "spend": {
        "used": {"amount_minor": 0, "currency": "USD", "exponent": 2},
        "limit": {"amount_minor": 0, "currency": "USD", "exponent": 2},
        "percent": 0,
        "severity": "normal",
        "enabled": False,
    },
    "extra_usage": None,
    "limits": [],
}
