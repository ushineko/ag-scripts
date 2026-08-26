"""Discovery of the Claude Code credential stores configured on this machine.

Claude Code selects its credential store with ``CLAUDE_SECURESTORAGE_CONFIG_DIR``,
which relocates ``.credentials.json`` **only** — the rest of ``~/.claude``
(projects, sessions, settings, skills) stays shared. That makes several OAuth
logins usable side by side, one per store.

That env var is per-process, so a running monitor cannot ask the system which
profiles exist. Discovery therefore keys on the directory convention the
``claude-max`` / ``claude-work`` wrappers establish:

    ~/.claude/.credentials.json                  -> the default store
    ~/.claude-credentials/<name>/.credentials.json -> one store per profile

Account *type* comes from ``subscriptionType`` inside the credential file, which
Claude Code writes at login. It is read here rather than from the usage API
because the API does not report it, and because a store whose token has expired
should still be labeled correctly.

This module is deliberately dependency-free — no Qt, no network — so it is unit
testable in isolation and can be copied verbatim into
``peripheral-battery-monitor`` (see spec 016 there).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

# Where the per-profile credential stores live. Matches the `claude-work`
# wrapper in dotfiles; overridable so tests need not touch a real home dir.
PROFILE_ROOT_ENV = "CLAUDE_USAGE_PROFILE_ROOT"
DEFAULT_PROFILE_ROOT = os.path.join(os.path.expanduser("~"), ".claude-credentials")

# The default store keeps no name of its own. It is reached by `claude-max`, so
# that is what it is called on screen.
DEFAULT_PROFILE_NAME = "max"
DEFAULT_STORE_DIR = os.path.join(os.path.expanduser("~"), ".claude")

CREDENTIALS_FILENAME = ".credentials.json"

# `subscriptionType` values Claude Code writes, mapped to display labels. The
# max_5x / max_20x variants are distinct plan tiers that both display as "Max".
_TYPE_LABELS = {
    "free": "Free",
    "pro": "Pro",
    "max": "Max",
    "max_5x": "Max",
    "max_20x": "Max",
    "team": "Team",
    "enterprise": "Enterprise",
}

# Shown when the store carries no subscriptionType, or one we do not recognize.
# Deliberately not "Unknown" — an unrecognized future tier is still an account,
# and the line should read as one.
UNKNOWN_TYPE_LABEL = "Account"

# Single-letter form used where horizontal space is scarce. Every tier Claude
# Code reports starts with a distinct letter, so the initial is unambiguous;
# an unrecognized tier gets "?" rather than a misleading letter.
UNKNOWN_TYPE_ABBREV = "?"


@dataclass(frozen=True)
class Account:
    """One configured credential store."""

    name: str
    """Profile name, e.g. ``max`` or ``work``."""

    store_dir: str
    """Directory holding ``.credentials.json`` (the CLAUDE_SECURESTORAGE_CONFIG_DIR value)."""

    subscription_type: str | None
    """Raw ``subscriptionType`` from the store, or None when absent."""

    is_default: bool
    """True for the default ``~/.claude`` store."""

    @property
    def credentials_path(self) -> str:
        return os.path.join(self.store_dir, CREDENTIALS_FILENAME)

    @property
    def type_label(self) -> str:
        """Display label for the account type, e.g. ``Max`` or ``Enterprise``."""
        return type_label(self.subscription_type)

    @property
    def type_abbrev(self) -> str:
        """One-letter account type, e.g. ``M`` for Max, ``E`` for Enterprise."""
        return type_abbrev(self.subscription_type)

    @property
    def label(self) -> str:
        """Full display label, e.g. ``work Enterprise``."""
        return f"{self.name} {self.type_label}"

    @property
    def short_label(self) -> str:
        """Compact display label, e.g. ``work E``, for tight layouts."""
        return f"{self.name} {self.type_abbrev}"


def type_label(subscription_type: str | None) -> str:
    """Map a raw ``subscriptionType`` to its display label."""
    if not subscription_type:
        return UNKNOWN_TYPE_LABEL
    return _TYPE_LABELS.get(subscription_type.lower(), UNKNOWN_TYPE_LABEL)


def type_abbrev(subscription_type: str | None) -> str:
    """One-letter form of the account type, for space-constrained displays."""
    label = type_label(subscription_type)
    if label == UNKNOWN_TYPE_LABEL:
        return UNKNOWN_TYPE_ABBREV
    return label[0]


def profile_root() -> str:
    """Directory holding the per-profile credential stores."""
    return os.environ.get(PROFILE_ROOT_ENV) or DEFAULT_PROFILE_ROOT


def default_store_dir() -> str:
    """The default credential store directory (``~/.claude``)."""
    return os.environ.get("CLAUDE_USAGE_DEFAULT_STORE") or DEFAULT_STORE_DIR


def read_subscription_type(store_dir: str) -> str | None:
    """Read ``subscriptionType`` from a store, or None if unreadable.

    A store that exists but cannot be parsed still counts as an account — it is
    reported with no type rather than dropped, so an expired or malformed login
    stays visible instead of silently vanishing from the display.
    """
    path = os.path.join(store_dir, CREDENTIALS_FILENAME)
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    oauth = data.get("claudeAiOauth")
    if not isinstance(oauth, dict):
        return None
    value = oauth.get("subscriptionType")
    return value if isinstance(value, str) else None


def _has_credentials(store_dir: str) -> bool:
    return os.path.isfile(os.path.join(store_dir, CREDENTIALS_FILENAME))


def discover() -> list[Account]:
    """Return every configured credential store, default first.

    A profile directory with no ``.credentials.json`` is skipped: the wrappers
    create the directory before the operator logs in, so an empty one means
    "not set up yet", not "broken account".

    Remaining profiles follow in alphabetical order so line order is stable
    between runs.
    """
    found: list[Account] = []

    default_dir = default_store_dir()
    if _has_credentials(default_dir):
        found.append(
            Account(
                name=DEFAULT_PROFILE_NAME,
                store_dir=default_dir,
                subscription_type=read_subscription_type(default_dir),
                is_default=True,
            )
        )

    root = profile_root()
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        entries = []

    for entry in entries:
        store_dir = os.path.join(root, entry)
        if not os.path.isdir(store_dir) or not _has_credentials(store_dir):
            continue
        # A profile literally named like the default would render two identical
        # labels; keep the default's and skip the duplicate.
        if any(a.name == entry for a in found):
            continue
        found.append(
            Account(
                name=entry,
                store_dir=store_dir,
                subscription_type=read_subscription_type(store_dir),
                is_default=False,
            )
        )

    return found


def discover_or_default() -> list[Account]:
    """Like :func:`discover`, but never returns an empty list.

    When no store is readable at all, callers still need one account to render
    the "not logged in" state against, rather than showing nothing.
    """
    found = discover()
    if found:
        return found
    return [
        Account(
            name=DEFAULT_PROFILE_NAME,
            store_dir=default_store_dir(),
            subscription_type=None,
            is_default=True,
        )
    ]
