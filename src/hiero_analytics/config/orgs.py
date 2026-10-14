"""The organisation registry — one declarative source of truth for every org.

Add an org by appending one ``OrgProfile`` here; everything org-shaped keys off
this table instead of scattering names through the codebase: which orgs the full
run renders, which publish a governance config (and from where), which get the
org-overview cards, and which are "governed" for the dashboard's ``@governed``
spec key.

``GITHUB_ORG`` selects the primary org and ``GITHUB_EXTRA_ORGS`` filters the
extra set, so existing workflows keep working: env is a view over this registry.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# The org the full run treats as primary: governance pipelines, governance
# config lookup, and the primary-org dashboards all resolve against it.
DEFAULT_PRIMARY_ORG = "hiero-ledger"


@dataclass(frozen=True)
class OrgProfile:
    """One GitHub organisation and what the analytics knows about it.

    Attributes:
        name: The GitHub org login.
        governed: Publishes a governance ``config.yaml``; governance pipelines
            (role coverage, affiliation, maintainer pipeline, HIPs) run for it
            and role labels resolve from its config.
        governance_url: Where ``config.yaml`` is fetched from when ``governed``.
        org_overview: Gets the org-overview cards (repos by contributor count,
            language mix, recent pushes) — the ``org_overview`` pipeline runs for
            it and the Contributors tab's ``@org_overview`` spec key applies.
        extra: Also rendered by the full run, after the primary org.
    """

    name: str
    governed: bool = False
    governance_url: str | None = None
    org_overview: bool = False
    extra: bool = False
    repo_categories: dict[str, str] = field(default_factory=dict)


ORGS: tuple[OrgProfile, ...] = (
    OrgProfile(
        name=DEFAULT_PRIMARY_ORG,
        governed=True,
        governance_url="https://raw.githubusercontent.com/hiero-ledger/governance/main/config.yaml",
    ),
    OrgProfile(
        name="hiero-hackers",
        org_overview=True,
        extra=True,
        # This org's repos that the ordered keyword rules in domain/repo_categories
        # would mis-bucket, keyed by bare repo name.
        repo_categories={
            "analytics": "Tooling / DevEx",
            "sdk-automations": "Tooling / DevEx",
            "hiero-maintainer-automation-prototype": "Tooling / DevEx",
            "hiero-did-sdk-rs": "Identity / DID",
            "hiero-sdk-csharp": "SDKs",
        },
    ),
)


def _primary_org() -> str:
    """The primary org: ``GITHUB_ORG`` when set, else the registry's default."""
    return os.getenv("GITHUB_ORG", DEFAULT_PRIMARY_ORG)


# The primary org of this process, resolved once at import — the default every
# org-shaped helper falls back to when not given an explicit org.
PRIMARY_ORG = _primary_org()


def profile_for(org: str) -> OrgProfile | None:
    """The registry entry for ``org``, or None when it is not registered."""
    for entry in ORGS:
        if entry.name == org:
            return entry
    return None


def is_governed(org: str) -> bool:
    """Whether ``org`` publishes a governance config the analytics can resolve."""
    profile = profile_for(org)
    return profile is not None and profile.governed


def is_primary(org: str) -> bool:
    """Whether ``org`` is the primary org of the current run.

    Reads the environment rather than the registry, so pointing the run at a
    different org with ``GITHUB_ORG`` moves the primary-org-only content (HIPs,
    the manual Discord export) with it.
    """
    return org == _primary_org()


def has_org_overview(org: str) -> bool:
    """Whether ``org`` gets the org-overview cards."""
    profile = profile_for(org)
    return profile is not None and profile.org_overview


def repo_category_overrides() -> dict[str, str]:
    """Every registered org's explicit repo->category entries, merged into one map.

    Kept out of :mod:`domain.repo_categories` so the per-org knowledge lives with
    the org that owns it; that module's ordered keyword rules stay the fallback.
    """
    overrides: dict[str, str] = {}
    for entry in ORGS:
        overrides.update(entry.repo_categories)
    return overrides


def org_names() -> tuple[str, ...]:
    """Every registered org name, registry order — primary first."""
    return tuple(entry.name for entry in ORGS)


def extra_orgs() -> list[str]:
    """Orgs the full run renders alongside the primary one.

    ``GITHUB_EXTRA_ORGS`` is a comma-separated allow-list over the registry's
    ``extra`` orgs; unset means the registry decides. One shared source, so the
    orchestrator and contributor heatmap can't drift apart.
    """
    registry = [entry.name for entry in ORGS if entry.extra]
    if "GITHUB_EXTRA_ORGS" not in os.environ:
        return registry
    requested = [org.strip() for org in os.getenv("GITHUB_EXTRA_ORGS", "").split(",") if org.strip()]
    dropped = [org for org in requested if org not in registry]
    if dropped:
        logger.warning(
            "GITHUB_EXTRA_ORGS names org(s) not in the registry's extra set, ignoring them: %s "
            "(register the org in config/orgs.py with extra=True to include it)",
            ", ".join(dropped),
        )
    return [org for org in registry if org in requested]


def governance_urls() -> dict[str, str]:
    """Per-org governance config sources, derived from the registry.

    ``GOVERNANCE_CONFIG_URL`` overrides the primary org's source (the CI
    escape hatch for testing a config change before it lands on the default
    branch); every other governed org keeps the URL its profile declares.
    """
    urls = {entry.name: entry.governance_url for entry in ORGS if entry.governance_url}
    if override := os.getenv("GOVERNANCE_CONFIG_URL"):
        urls[_primary_org()] = override
    return urls
