"""The organisation registry — one declarative source of truth for every org.

Add an org by appending one ``OrgProfile`` here; everything org-shaped keys off
this table instead of scattering names through the codebase: which orgs the full
run renders, which publish a governance config (and from where), which
pipelines run for each org, which dashboard cards it gets, and how the
dashboard names and brands it.

Capabilities are the join between the three places that care about an org:

- a pipeline declares the capabilities it ``requires`` (``pipelines/__init__``),
  and the full run only schedules it for orgs that have them;
- a dashboard family keys cards by ``"@<capability>"`` (``dashboard_spec``), and
  an org gets the cards for the capabilities it has;
- the profile below says which capabilities an org has.

The environment is a *view* over the registry, never a second roster:
``GITHUB_ORG`` picks the primary org, ``GITHUB_EXTRA_ORGS`` narrows the extra
set, and ``HIERO_ANALYTICS_TRIAL_ORGS`` adds unregistered orgs to one run for
evaluation (the scheduled workflow does not publish such a run).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# The org the full run treats as primary when GITHUB_ORG is unset: repo-scoped
# pipelines (GITHUB_REPO) run for it, and it leads the dashboard's org list.
DEFAULT_PRIMARY_ORG = "hiero-ledger"

# Capability names. A pipeline's ``requires`` and a dashboard card's
# ``"@<name>"`` key use exactly these strings.
GOVERNED = "governed"
ORG_OVERVIEW = "org_overview"
HIPS = "hips"
DISCORD = "discord"
CAPABILITIES = frozenset({GOVERNED, ORG_OVERVIEW, HIPS, DISCORD})


@dataclass(frozen=True)
class OrgProfile:
    """One GitHub organisation and what the analytics knows about it.

    Attributes:
        name: The GitHub org login, spelt exactly as GitHub returns it: output
            paths, dataset files and ``owner/repo`` joins are case-sensitive.
        display_name: How the dashboard labels the org; the login when unset.
        governed: Publishes a governance config (``teams`` + ``repositories``);
            the governance pipelines run for it and its people get role labels.
        governance_url: Where that config is fetched from when ``governed``.
        blanket_teams: Org-wide teams granted on (nearly) every repo. Excluded
            from per-repo role holders so they don't stamp the same people onto
            every repo; credited as maintainers only where a repo has no domain
            maintainer team.
        org_overview: Gets the org-overview cards (repos by contributor count,
            language mix, recent pushes).
        extra: Rendered by the full run alongside the primary org.
        hip_proposals_repo: ``owner/repo`` holding the org's improvement
            proposals; setting it gives the org the HIPs tab.
        discord: Owns the manually exported Discord tables (Community tab).
        brand: Key of the logo set under ``web/public/brand/<brand>/``; the
            default Hiero mark when unset.
        repo_categories: Bare repo name -> category, for this org's repos the
            keyword rules in ``domain.repo_categories`` would mis-bucket.
    """

    name: str
    display_name: str | None = None
    governed: bool = False
    governance_url: str | None = None
    blanket_teams: frozenset[str] = frozenset()
    org_overview: bool = False
    extra: bool = False
    hip_proposals_repo: str | None = None
    discord: bool = False
    brand: str | None = None
    repo_categories: Mapping[str, str] = field(default_factory=dict)

    @property
    def capabilities(self) -> frozenset[str]:
        """The capabilities this org has, by the names in :data:`CAPABILITIES`."""
        flags = {
            GOVERNED: self.governed,
            ORG_OVERVIEW: self.org_overview,
            HIPS: self.hip_proposals_repo is not None,
            DISCORD: self.discord,
        }
        return frozenset(name for name, present in flags.items() if present)

    @property
    def label(self) -> str:
        """The name the dashboard shows for this org."""
        return self.display_name or self.name


ORGS: tuple[OrgProfile, ...] = (
    OrgProfile(
        name=DEFAULT_PRIMARY_ORG,
        governed=True,
        governance_url="https://raw.githubusercontent.com/hiero-ledger/governance/main/config.yaml",
        blanket_teams=frozenset({"github-maintainers", "security-maintainers", "lf-staff", "tsc", "hiero-triage"}),
        hip_proposals_repo="hiero-ledger/hiero-improvement-proposals",
        discord=True,
    ),
    OrgProfile(
        name="hiero-hackers",
        org_overview=True,
        extra=True,
        repo_categories={
            "analytics": "Tooling / DevEx",
            "sdk-automations": "Tooling / DevEx",
            "hiero-maintainer-automation-prototype": "Tooling / DevEx",
            "hiero-did-sdk-rs": "Identity / DID",
            "hiero-sdk-csharp": "SDKs",
        },
    ),
)


def _env_list(name: str) -> list[str]:
    """A comma-separated environment variable as a list of non-empty names."""
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


def primary_org() -> str:
    """The primary org of this run: ``GITHUB_ORG`` when set, else the default.

    Read at call time, so a test or a one-off run can repoint it; modules that
    need an import-time default for a function signature use ``paths.ORG``.
    """
    return os.getenv("GITHUB_ORG") or DEFAULT_PRIMARY_ORG


def profile_for(org: str) -> OrgProfile | None:
    """The registry entry for ``org``, or None when it is not registered."""
    for entry in ORGS:
        if entry.name == org:
            return entry
    return None


def profile_or_default(org: str) -> OrgProfile:
    """The registry entry for ``org``, or an ungoverned, capability-free profile.

    Unregistered orgs reach the run only as trial orgs or a hand-set
    ``GITHUB_ORG``; treating them as plain orgs keeps every code path total.
    """
    return profile_for(org) or OrgProfile(name=org)


def capabilities_of(org: str) -> frozenset[str]:
    """What ``org`` provides; empty for an unregistered org."""
    return profile_or_default(org).capabilities


def is_governed(org: str) -> bool:
    """Whether ``org`` publishes a governance config the analytics can resolve."""
    return GOVERNED in capabilities_of(org)


def has_org_overview(org: str) -> bool:
    """Whether ``org`` gets the org-overview cards."""
    return ORG_OVERVIEW in capabilities_of(org)


def blanket_teams(org: str) -> frozenset[str]:
    """``org``'s org-wide teams (empty for an unregistered org)."""
    return profile_or_default(org).blanket_teams


def hip_proposals_repo(org: str) -> str | None:
    """Where ``org``'s improvement proposals live; ``HIP_PROPOSALS_REPO`` overrides."""
    profile = profile_or_default(org)
    if profile.hip_proposals_repo is None:
        return None
    return os.getenv("HIP_PROPOSALS_REPO") or profile.hip_proposals_repo


def discord_org() -> str | None:
    """The org that owns the Discord export tables, or None when none does."""
    return next((entry.name for entry in ORGS if entry.discord), None)


def repo_category_overrides() -> dict[str, str]:
    """Every registered org's explicit repo->category entries, merged into one map.

    Kept here so per-org knowledge lives with the org that owns it; callers
    hand the map to ``domain.repo_categories.categorize_repo``, whose keyword
    rules stay the fallback.
    """
    overrides: dict[str, str] = {}
    for entry in ORGS:
        overrides.update(entry.repo_categories)
    return overrides


def org_names() -> tuple[str, ...]:
    """Every registered org name, in registry order."""
    return tuple(entry.name for entry in ORGS)


def extra_orgs() -> list[str]:
    """Registered orgs the full run renders alongside the primary one.

    ``GITHUB_EXTRA_ORGS`` is a comma-separated allow-list over the registry's
    ``extra`` orgs; unset means the registry decides, and an empty value
    renders none. Names it lists that are not registered extras are ignored
    with a warning; use ``HIERO_ANALYTICS_TRIAL_ORGS`` to evaluate a new org.
    """
    primary = primary_org()
    registry = [entry.name for entry in ORGS if entry.extra and entry.name != primary]
    if "GITHUB_EXTRA_ORGS" not in os.environ:
        return registry
    requested = _env_list("GITHUB_EXTRA_ORGS")
    dropped = [org for org in requested if org not in registry and org != primary]
    if dropped:
        logger.warning(
            "GITHUB_EXTRA_ORGS names org(s) that are not registered extras, ignoring them: %s "
            "(register the org in config/orgs.py with extra=True, or set HIERO_ANALYTICS_TRIAL_ORGS to try it once)",
            ", ".join(dropped),
        )
    return [org for org in registry if org in requested]


def trial_orgs() -> list[str]:
    """Orgs added to this run only, from ``HIERO_ANALYTICS_TRIAL_ORGS``.

    For evaluating an org before registering it: it runs every pipeline that
    needs no capability, under its own name, as an ungoverned org.
    """
    trials = _env_list("HIERO_ANALYTICS_TRIAL_ORGS")
    unregistered = [org for org in trials if profile_for(org) is None]
    if unregistered:
        logger.info("Trial org(s) for this run, treated as ungoverned: %s", ", ".join(unregistered))
    return trials


def rendered_orgs() -> list[str]:
    """Every org this run renders: primary first, then extras, then trial orgs."""
    return list(dict.fromkeys([primary_org(), *extra_orgs(), *trial_orgs()]))


def governance_urls() -> dict[str, str]:
    """Per-org governance config sources, derived from the registry.

    ``GOVERNANCE_CONFIG_URL`` overrides the primary org's source (the CI
    escape hatch for testing a config change before it lands on the default
    branch); every other governed org keeps the URL its profile declares.
    """
    urls = {entry.name: entry.governance_url for entry in ORGS if entry.governance_url}
    if override := os.getenv("GOVERNANCE_CONFIG_URL"):
        urls[primary_org()] = override
    return urls
