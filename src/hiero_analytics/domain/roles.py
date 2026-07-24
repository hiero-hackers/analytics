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
