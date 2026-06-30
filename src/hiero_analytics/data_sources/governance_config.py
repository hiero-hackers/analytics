"""Helpers for mapping governance config teams to repo-scoped contributor roles."""

from __future__ import annotations

import os
from collections import defaultdict
from typing import Any

import requests
import yaml

from hiero_analytics.config.github import HTTP_TIMEOUT_SECONDS
from hiero_analytics.domain.bots import is_bot_login

GOVERNANCE_CONFIG_URL = os.getenv(
    "GOVERNANCE_CONFIG_URL",
    "https://raw.githubusercontent.com/hiero-ledger/governance/main/config.yaml",
)

ROLE_PRIORITY = {
    "general_user": 0,
    "triage": 1,
    "committer": 2,
    "maintainer": 3,
}


# Org-wide "blanket" teams: assigned to (nearly) every repo, so counting them as a
# repo's role-holders would stamp the same handful of people onto all repos and
# drown out domain-specific maintainership. Excluded from domain repos, but used as
# a maintainer fallback for org/meta repos that have no domain maintainer team.
BLANKET_TEAMS = frozenset(
    {"github-maintainers", "security-maintainers", "lf-staff", "tsc", "hiero-triage"}
)

def _normalize_username(user: str) -> str:
    """Normalize GitHub logins for case-insensitive matching."""
    return user.strip().lower()


def _resolve_roles(
    assignments: dict[str, Any],
    team_members: dict[str, set[str]],
    *,
    skip: frozenset[str] = frozenset(),
    only: frozenset[str] | None = None,
) -> dict[str, str]:
    """Resolve ``user -> highest role`` for one repo's team assignments.

    Skips automation teams, bot logins, teams in ``skip``, and (when ``only`` is
    given) any team not in it.
    """
    roles: dict[str, str] = {}
    for team_name, permission in assignments.items():
        if not isinstance(team_name, str) or "automation" in team_name.lower():
            continue
        if only is not None and team_name not in only:
            continue
        if team_name in skip:
            continue
        role = permission_to_role(permission)
        if role is None:
            continue
        for user in team_members.get(team_name, set()):
            if is_bot_login(user):
                continue
            current = roles.get(user)
            if current is None or ROLE_PRIORITY[role] > ROLE_PRIORITY[current]:
                roles[user] = role
    return roles


def fetch_governance_config(url: str = GOVERNANCE_CONFIG_URL) -> dict[str, Any]:
    """Fetch and parse the Hiero governance config file."""
    response = requests.get(url, timeout=HTTP_TIMEOUT_SECONDS)
    response.raise_for_status()
    data = yaml.safe_load(response.text)

    if not isinstance(data, dict):
        raise ValueError("Governance config did not parse into a mapping")

    return data


def build_team_membership(config: dict[str, Any]) -> dict[str, set[str]]:
    """Map each governance team to its member logins (maintainers + members)."""
    membership: dict[str, set[str]] = {}
    for team in config.get("teams", []):
        if not isinstance(team, dict):
            continue
        name = team.get("name")
        if not isinstance(name, str):
            continue
        members: set[str] = set()
        for field in ("maintainers", "members"):
            values = team.get(field, [])
            if isinstance(values, list):
                members.update(
                    _normalize_username(user) for user in values if isinstance(user, str) and user
                )
        membership[name] = members
    return membership


def build_repo_role_lookup(config: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Build repo -> user -> highest governance role from explicit per-repo teams.

    Applies each repo's listed team→permission grants directly (GitHub's real model),
    taking the highest role per user — so a team granted to several repos is counted on
    all of them. Org-wide *blanket* teams (``BLANKET_TEAMS``) and bot/automation teams
    are excluded from domain repos, so they don't stamp the same people onto every repo.
    As a fallback, blanket *maintain* teams are credited on repos that have no domain
    maintainer team (e.g. ``governance``, ``.github``), so org-governed repos aren't
    shown as unmaintained.
    """
    team_members = build_team_membership(config)

    repo_roles: dict[str, dict[str, str]] = {}
    for repo in config.get("repositories", []):
        if not isinstance(repo, dict):
            continue
        repo_name = repo.get("name")
        assignments = repo.get("teams", {})
        if not isinstance(repo_name, str) or not isinstance(assignments, dict):
            continue

        roles = _resolve_roles(assignments, team_members, skip=BLANKET_TEAMS)
        # Org/meta repos have no domain maintainer team — credit the blanket maintain
        # teams there so they're not misreported as having zero maintainers.
        if not any(role == "maintainer" for role in roles.values()):
            for user, role in _resolve_roles(assignments, team_members, only=BLANKET_TEAMS).items():
                if role != "maintainer":
                    continue  # credit blanket *maintainers* only — not triage/write holders
                current = roles.get(user)
                if current is None or ROLE_PRIORITY[role] > ROLE_PRIORITY[current]:
                    roles[user] = role

        repo_roles[repo_name] = roles

    return repo_roles


def permission_to_role(permission: Any) -> str | None:
    """Normalize governance repo permissions into chart roles."""
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


def summarize_role_counts(repo_role_lookup: dict[str, dict[str, str]]) -> dict[str, int]:
    """Return distinct user counts by highest role across all repositories."""
    users: dict[str, str] = {}
    for repo_lookup in repo_role_lookup.values():
        for user, role in repo_lookup.items():
            current_role = users.get(user)
            if current_role is None or ROLE_PRIORITY[role] > ROLE_PRIORITY[current_role]:
                users[user] = role

    counts: dict[str, int] = defaultdict(int)
    for role in users.values():
        counts[role] += 1
    return dict(counts)


def count_distinct_role_holders_by_role(
    repo_role_lookup: dict[str, dict[str, str]],
) -> dict[str, int]:
    """Return distinct user counts for each role across all repositories."""
    users_by_role: dict[str, set[str]] = defaultdict(set)
    for repo_lookup in repo_role_lookup.values():
        for user, role in repo_lookup.items():
            users_by_role[role].add(user)

    return {role: len(users) for role, users in users_by_role.items()}
