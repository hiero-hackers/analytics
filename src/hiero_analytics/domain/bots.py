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


# Weaker automation signals than is_bot_login's suffix/name-list checks. Order
# only matters when one login has several tokens each matching a different
# signal (e.g. "ci-svc-bot") — the more descriptive one is reported first.
SUSPECT_SIGNALS = ("automation", "actions", "service", "auto", "bot", "svc", "ci")

_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def _tokens(name: str) -> set[str]:
    """Split a login on non-alphanumeric separators (-, _, .) into word-ish chunks."""
    return {t for t in _TOKEN_SPLIT.split(name) if t}


def bot_suspect_signal(login: str) -> str | None:
    """The weak automation signal a login trips, or ``None`` if it trips none.

    Only meaningful for logins ``is_bot_login`` does *not* already exclude —
    those are automation accounts by the canonical policy already, not
    suspects. Intended for a review CSV: a hit here doesn't mean "bot", it
    means "a maintainer should take a look".

    A signal only counts if it's a *whole* token on its own (a login split on
    -, _, .) — not a substring anywhere within a token, prefix or suffix
    included. Earlier versions allowed a prefix/suffix match, on the theory
    that a login like "robert-downey" merely *containing* "ci" mid-word was
    the only real risk. Real data proved that wrong: checked against this
    project's actual contributor logins, "ci" as a prefix/suffix flagged
    people named things like "cijujohn" and "joshmarinacci", and "bot" as a
    suffix flagged "mrswastik-robot" — a real, active open-source contributor
    whose handle happens to end in a word that ends in "bot". None of those
    are automation accounts; all of them were false positives with zero
    offsetting true positives found. Requiring an exact token match keeps
    both of the issue's motivating examples — "hiero-automation" (token
    "automation") and "sdk-release-ci" (token "ci") — while refusing to match
    "ci" or "bot" glued onto the rest of someone's name, which is exactly
    where all the observed noise came from.
    """
    name = login.strip().lower()
    if is_bot_login(name):
        return None
    tokens = _tokens(name)
    for signal in SUSPECT_SIGNALS:
        if signal in tokens:
            return signal
    return None
