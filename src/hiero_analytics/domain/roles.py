"""Governance role vocabulary — the ranking and the permission mapping.

These describe what the roles *are* (their seniority order and how a GitHub
repo permission maps to one), independent of where a governance config is
fetched from. The analysis and dashboard layers rank holders by this priority;
``data_sources.governance_config`` uses the permission mapping when resolving a
config into per-repo roles.
"""

from __future__ import annotations

from typing import Any

# Seniority order for governance roles; higher wins when a person holds several.
ROLE_PRIORITY = {
    "general_user": 0,
    "triage": 1,
    "committer": 2,
    "maintainer": 3,
}


def highest_role_holders(role_lookup: dict[str, dict[str, str]], role: str) -> set[str]:
    """Logins whose *highest* role anywhere in the org is ``role``.

    Reducing each person to their most senior role keeps the role populations
    disjoint, so a committer here is someone with write access and no maintainer
    seat in any repository — the same definition the role metric tiles use.
    """
    highest: dict[str, str] = {}
    for holders in role_lookup.values():
        for login, held in holders.items():
            current = highest.get(login)
            if current is None or ROLE_PRIORITY.get(held, 0) > ROLE_PRIORITY.get(current, 0):
                highest[login] = held
    return {login for login, held in highest.items() if held == role}


def highest_role_lookup(role_lookup: dict[str, dict[str, str]], role: str) -> dict[str, dict[str, str]]:
    """``role_lookup`` keeping only the people whose highest role anywhere is ``role``.

    Per-repo views built from this count a person in a repo only when they hold
    ``role`` there *and* hold nothing more senior anywhere else, so the per-repo
    breakdowns describe the same population as the org-wide one.
    """
    holders = highest_role_holders(role_lookup, role)
    return {repo: {login: held for login, held in h.items() if login in holders} for repo, h in role_lookup.items()}


def permission_to_role(permission: Any) -> str | None:
    """Normalize a GitHub repo permission into a governance role, or None."""
    if not isinstance(permission, str):
        return None

    normalized = permission.lower()
    if normalized == "triage":
        return "triage"
    if normalized == "write":
        return "committer"
    if normalized in {"maintain", "admin"}:
        return "maintainer"
    return None
