"""Identify automation accounts (bots) so they can be excluded from people metrics.

A GitHub App's GraphQL login doesn't always carry a ``[bot]`` suffix (e.g. the
login is ``dependabot``, not ``dependabot[bot]``), so a name list backs up the
suffix checks. Matching is case-insensitive.
"""

from __future__ import annotations

# Named automation accounts whose login carries no ``[bot]``/``-bot`` suffix; the
# suffixed ones (``*-bot``, ``*[bot]``) are caught by is_bot_login regardless.
BOT_LOGINS = frozenset(
    {
        "dependabot",
        "dependabot-preview",
        "coderabbit",
        "coderabbitai",
        "copilot-pull-request-reviewer",
        "github-actions",
        "renovate",
        "swirlds-automation",
        "trunk-io",
    }
)


def is_bot_login(login: str) -> bool:
    """True when a login is an automation account rather than a person."""
    name = login.strip().lower()
    return name.endswith("[bot]") or name.endswith("-bot") or name in BOT_LOGINS


# Weaker automation signals than is_bot_login's suffix/name-list checks — plain
# substrings, so they will false-positive on real names (e.g. "marcia" contains
# "ci"). That's fine here: these are for a human-reviewed suspects list, not for
# exclusion, so a false positive costs a reviewer a glance rather than silently
# mislabeling a person. Ordered longest/most-specific first so a login matching
# several (e.g. "hiero-automation" also contains "auto") reports the most
# descriptive one rather than a generic substring of it.
SUSPECT_SIGNALS = ("automation", "actions", "service", "auto", "bot", "svc", "ci")


def bot_suspect_signal(login: str) -> str | None:
    """The weak automation signal a login trips, or ``None`` if it trips none.

    Only meaningful for logins ``is_bot_login`` does *not* already exclude —
    those are automation accounts by the canonical policy already, not
    suspects. Intended for a review CSV: a hit here doesn't mean "bot", it
    means "a maintainer should take a look".
    """
    name = login.strip().lower()
    if is_bot_login(name):
        return None
    for signal in SUSPECT_SIGNALS:
        if signal in name:
            return signal
    return None
