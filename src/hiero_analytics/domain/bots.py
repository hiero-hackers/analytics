"""Identify automation accounts (bots) so they can be excluded from people metrics.

A GitHub App's GraphQL login doesn't always carry a ``[bot]`` suffix (e.g. the
login is ``dependabot``, not ``dependabot[bot]``), so a name list backs up the
suffix checks. Matching is case-insensitive.
"""

from __future__ import annotations

import re

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


# Weaker automation signals than is_bot_login's suffix/name-list checks. Ordered
# longest/most-specific first so a login matching several (e.g.
# "hiero-automation" also matches "auto") reports the most descriptive one
# rather than a generic prefix/suffix of it.
SUSPECT_SIGNALS = ("automation", "actions", "service", "auto", "bot", "svc", "ci")

_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def _tokens(name: str) -> list[str]:
    """Split a login on non-alphanumeric separators (-, _, .) into word-ish chunks."""
    return [t for t in _TOKEN_SPLIT.split(name) if t]


def bot_suspect_signal(login: str) -> str | None:
    """The weak automation signal a login trips, or ``None`` if it trips none.

    Only meaningful for logins ``is_bot_login`` does *not* already exclude —
    those are automation accounts by the canonical policy already, not
    suspects. Intended for a review CSV: a hit here doesn't mean "bot", it
    means "a maintainer should take a look".

    A signal only counts as the prefix or suffix of a token (a login split on
    -, _, .), never a mid-word substring — plain substring matching flagged
    real names purely because a signal's letters happened to sit somewhere in
    the middle (e.g. "viniciusjssouza" contains "ci"). Anchoring to token edges
    cuts that out while still catching the motivating cases: "hiero-automation"
    (suffix of a token), "sdk-release-ci" (suffix), "botrunner" (prefix, single
    token), "sdk-bot-helper" (a whole token, which is trivially both). It won't
    catch everything — a short signal like "ci" can still be a real prefix or
    suffix of an unrelated name — but that's an explicit tradeoff per review:
    false positives from a genuine edge match are acceptable, false positives
    from a signal merely appearing somewhere inside a word are not.
    """
    name = login.strip().lower()
    if is_bot_login(name):
        return None
    tokens = _tokens(name)
    for signal in SUSPECT_SIGNALS:
        if any(token.startswith(signal) or token.endswith(signal) for token in tokens):
            return signal
    return None
