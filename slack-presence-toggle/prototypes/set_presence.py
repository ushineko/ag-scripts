#!/usr/bin/env python3
"""Prototype B: validate the Slack users.setPresence round-trip.

Reads a User OAuth Token (xoxp-...) from a file, sets presence to either
"auto" or "away", then reads it back to confirm Slack accepted the change.

Usage:
    python3 set_presence.py auto
    python3 set_presence.py away
    python3 set_presence.py --token-file /path/to/token away

Default token path: ~/.config/slack-presence-toggle/token
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_TOKEN_FILE = Path.home() / ".config/slack-presence-toggle/token"
SLACK_API = "https://slack.com/api"


def slack_call(token: str, method: str, params: dict[str, str] | None = None) -> dict:
    """POST to a Slack API method using form-encoded body."""
    url = f"{SLACK_API}/{method}"
    body = urllib.parse.urlencode(params or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("presence", choices=["auto", "away"])
    parser.add_argument(
        "--token-file",
        type=Path,
        default=DEFAULT_TOKEN_FILE,
        help=f"Path to file containing the xoxp- token (default: {DEFAULT_TOKEN_FILE})",
    )
    args = parser.parse_args()

    if not args.token_file.exists():
        print(f"Token file not found: {args.token_file}", file=sys.stderr)
        return 1

    token = args.token_file.read_text().strip()
    if not token.startswith("xoxp-"):
        print(
            f"Token in {args.token_file} doesn't look like a User OAuth Token "
            "(should start with xoxp-)",
            file=sys.stderr,
        )
        return 1

    # 1. Confirm token works and identify whose presence we're touching.
    auth = slack_call(token, "auth.test")
    if not auth.get("ok"):
        print(f"auth.test failed: {auth}", file=sys.stderr)
        return 1
    print(f"Authenticated as user={auth['user']} team={auth['team']}")

    # 2. Read current presence.
    before = slack_call(token, "users.getPresence")
    print(f"Before: {json.dumps(before)}")

    # 3. Set requested presence.
    set_resp = slack_call(token, "users.setPresence", {"presence": args.presence})
    print(f"setPresence({args.presence!r}): {json.dumps(set_resp)}")
    if not set_resp.get("ok"):
        print("setPresence rejected the change", file=sys.stderr)
        return 1

    # 4. Confirm.
    after = slack_call(token, "users.getPresence")
    print(f"After:  {json.dumps(after)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
