"""Sanity checks on edited save contents.

The rule that matters: only warn about ids the *user* introduced. Ids the game
itself wrote are correct by definition, even when they do not appear in any
vocabulary we can harvest - composite ids like "SantaHat_hat" and internal-only
achievement ids like "a_skin_foxKills" are real but absent from both the
metadata literals and Steam's schema. Validating everything produces a dozen
false alarms and trains the user to ignore the warning; validating only
additions produces none.

This catches the failure mode that actually bites: typing a plausible-looking id
that the game does not recognise. The game persists such an entry happily and
ignores it forever, so nothing on screen distinguishes "wrong id" from "editing
this field does not work".
"""

# Fields whose entries are game identifiers worth checking.
ID_LIST_FIELDS = ("purchases", "achievements", "claimedAchievements", "inactivated")


def added_entries(original: dict, current: dict, fields=ID_LIST_FIELDS) -> dict[str, list[str]]:
    """Entries present in `current` but not in the originally loaded `original`."""
    out = {}
    for field in fields:
        before, after = original.get(field), current.get(field)
        if not isinstance(before, list) or not isinstance(after, list):
            continue
        added = [v for v in after if v not in before]
        if added:
            out[field] = added
    return out


def unknown_additions(original: dict, current: dict, known: set[str],
                      fields=ID_LIST_FIELDS) -> dict[str, list[str]]:
    """User-added ids that the game does not appear to recognise.

    Empty `known` means the vocabulary could not be harvested (game not
    installed); in that case report nothing rather than flagging everything.
    """
    if not known:
        return {}
    out = {}
    for field, added in added_entries(original, current, fields).items():
        unknown = [v for v in added if v not in known]
        if unknown:
            out[field] = unknown
    return out


def describe(unknown: dict[str, list[str]]) -> str:
    """One-line summary for a status bar."""
    if not unknown:
        return ""
    parts = [f"{field}: {', '.join(values)}" for field, values in unknown.items()]
    return "unrecognized id(s) - " + " | ".join(parts)


def touches_steam_achievements(original: dict, current: dict) -> bool:
    """True if the edit adds achievement ids.

    The local achievement lists are mirrored up to Steam, so adding one can put
    an achievement on the user's public profile that they did not earn. Verified
    behaviour, not speculation - it happened while reverse-engineering this
    game's unlock chain.
    """
    added = added_entries(original, current, ("achievements", "claimedAchievements"))
    return bool(added)
