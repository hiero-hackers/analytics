"""Helpers for mapping governance config teams to repo-scoped contributor roles."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import requests
import yaml

from hiero_analytics.config.github import HTTP_TIMEOUT_SECONDS
from hiero_analytics.config.paths import DATASETS_DIR, ORG, dataset_path
from hiero_analytics.data_sources.dataset_store import offline_mode_enabled
from hiero_analytics.domain.bots import is_bot_login
from hiero_analytics.domain.roles import ROLE_PRIORITY, permission_to_role

logger = logging.getLogger(__name__)

# Per-org governance config sources. Only governed orgs appear here; an org
# without an entry (e.g. the composition org) has no governance roles and
# fetches an empty config rather than inheriting another org's. The
# GOVERNANCE_CONFIG_URL env var overrides the configured primary org's source.
GOVERNANCE_CONFIG_URLS: dict[str, str] = {
    "hiero-ledger": "https://raw.githubusercontent.com/hiero-ledger/governance/main/config.yaml",
}
if _url_override := os.getenv("GOVERNANCE_CONFIG_URL"):
    GOVERNANCE_CONFIG_URLS[ORG] = _url_override

# Org-wide "blanket" teams: assigned to (nearly) every repo, so counting them as a
# repo's role-holders would stamp the same handful of people onto all repos and
# drown out domain-specific maintainership. Excluded from domain repos, but used as
# a maintainer fallback for org/meta repos that have no domain maintainer team.
BLANKET_TEAMS = frozenset({"github-maintainers", "security-maintainers", "lf-staff", "tsc", "hiero-triage"})


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


def _validate_governance_config(data: Any) -> dict[str, Any]:
    """Return a parsed governance mapping or reject an invalid payload."""
    if not isinstance(data, dict):
        raise ValueError("Governance config did not parse into a mapping")
    return data


def fetch_governance_config(
    org: str = ORG,
    *,
    url: str | None = None,
    snapshot_path: Path | None = None,
) -> dict[str, Any]:
    """Fetch ``org``'s governance config live, or load its validated snapshot offline.

    The source resolves from ``GOVERNANCE_CONFIG_URLS`` (or the explicit ``url``);
    an org with no configured source is ungoverned and gets an empty config.
    Snapshots are org-scoped so two governed orgs can never collide.
    """
    source = url or GOVERNANCE_CONFIG_URLS.get(org)
    if source is None and snapshot_path is None:
        logger.info("No governance config source for org %s; treating it as ungoverned", org)
        return {}

    path = snapshot_path or dataset_path("governance_config", org)
    if offline_mode_enabled():
        if snapshot_path is None and not path.exists():
            # Transitional fallback: snapshots written before org-scoping used one
            # un-scoped filename. Remove once refreshed CI caches carry the
            # org-scoped name. Never applied to an explicitly given path.
            legacy = DATASETS_DIR / "governance_config.json"
            if legacy.exists():
                path = legacy
        if not path.exists():
            raise RuntimeError(f"Offline mode requires a governance config snapshot at {path}")
        try:
            return _validate_governance_config(json.loads(path.read_text(encoding="utf-8")))
        # ValueError covers both a JSON parse failure and a decoded-but-invalid
        # payload (_validate_governance_config), so the offline branch always fails
        # with a clear RuntimeError rather than leaking a raw ValueError.
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"Offline governance config snapshot is invalid: {path}") from exc

    response = requests.get(source, timeout=HTTP_TIMEOUT_SECONDS)
    response.raise_for_status()
    data = _validate_governance_config(yaml.safe_load(response.text))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
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
                members.update(_normalize_username(user) for user in values if isinstance(user, str) and user)
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
