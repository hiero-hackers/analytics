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
