"""Build the organisation-diversity tables for the org.

Reads the curated ``data/affiliations.yaml`` map and the org's governance config,
classifies every role-holder by employer (or independent / unknown), and writes a
set of org-scoped tables per role tab (maintainers, committers) plus the
role-agnostic team tables. Per role, suffixed ``_committers`` for the second tab:

- ``<role>_affiliations.csv`` — login, organisation, status (raw cross-reference)
- ``affiliation_distribution.csv`` — distinct holders by organisation
- ``repo_affiliation_composition.csv`` — per-repo employer mix
- ``repo_affiliation_diversity.csv`` and ``single_employer_repos_by_org.csv``

Concentration (HHI, top-org share, coverage) is logged per role. Affiliation needs
no network beyond the governance config the other governance pipelines already
fetch, so this stays cheap and deterministic.
"""

from __future__ import annotations

import logging

from hiero_analytics.analysis.affiliation import (
    AFFILIATIONS_PATH,
    build_affiliation_distribution,
    build_org_activity_heatmap,
    build_repo_affiliation_diversity,
    build_repo_org_composition,
    build_single_employer_repo_counts,
    build_single_employer_team_counts,
    build_team_affiliation_diversity,
    build_team_org_composition,
    classify_role_holders,
    known_share_pct,
    load_affiliations,
    load_manual_logins,
    role_column,
    summarize_affiliation,
)
from hiero_analytics.analysis.contributor_heatmap import (
    build_activity_heatmap_dataframe,
    build_repo_activity_heatmap,
    build_team_activity_heatmap,
)
from hiero_analytics.config.analysis import AFFILIATION_MIN_KNOWN_SHARE_PCT
from hiero_analytics.config.paths import ORG, ensure_org_dirs
from hiero_analytics.data_sources.governance_config import (
    build_repo_role_lookup,
    build_team_membership,
    fetch_governance_config,
)
from hiero_analytics.domain.roles import highest_role_holders, highest_role_lookup
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.pipelines._shared import load_contributor_activity, shared_client

logger = logging.getLogger(__name__)

# The dashboard's role tabs, as (role, output-filename suffix). Maintainer keeps
# the bare filenames it has always had; every other role is suffixed, so adding a
# tab never renames an existing artifact.
ROLE_VARIANTS = [("maintainer", ""), ("committer", "_committers")]


def _write_distribution(classified, data_dir, *, suffix, value_col):
    """Role-holders-by-organisation table over people with resolved affiliations."""
    distribution = build_affiliation_distribution(classified, value_col=value_col, include_unknown=False)
    save_dataframe(distribution, data_dir / f"affiliation_distribution{suffix}.csv")


def _write_repo_composition(role_lookup, affiliations, data_dir, *, role, suffix):
    """Per-repo organisation-mix table for one role's holders; skipped when no segments."""
    composition, segments = build_repo_org_composition(role_lookup, affiliations, role=role)
    if segments:
        save_dataframe(composition, data_dir / f"repo_affiliation_composition{suffix}.csv")


def _write_team_composition(team_membership, affiliations, data_dir, *, suffix):
    """Per-team organisation-mix table; skipped when no segments."""
    composition, segments = build_team_org_composition(team_membership, affiliations)
    if segments:
        save_dataframe(composition, data_dir / f"team_affiliation_composition{suffix}.csv")


def _write_single_employer_teams(team_membership, affiliations, data_dir, *, suffix):
    """Single-employer teams by controlling org; skipped when there are none."""
    counts = build_single_employer_team_counts(build_team_affiliation_diversity(team_membership, affiliations))
    if not counts.empty:
        save_dataframe(counts, data_dir / f"single_employer_teams_by_org{suffix}.csv")


def _write_repo_diversity(role_lookup, affiliations, data_dir, *, role, suffix):
    """Per-repo diversity table plus its single-employer-repos-by-org companion table."""
    diversity = build_repo_affiliation_diversity(role_lookup, affiliations, role=role)
    save_dataframe(diversity, data_dir / f"repo_affiliation_diversity{suffix}.csv")
    counts = build_single_employer_repo_counts(diversity, count_col=role_column(role))
    if not counts.empty:
        save_dataframe(counts, data_dir / f"single_employer_repos_by_org{suffix}.csv")
    if not diversity.empty:
        logger.info(
            "Repo diversity (%s): %d of %d repos are single-employer (one org holds every seat)",
            role,
            int((diversity["distinct_orgs"] <= 1).sum()),
            len(diversity),
        )


def _write_activity_heatmaps(records, role_lookup, team_membership, affiliations, org_data_dir):
    """Activity heatmaps at three aggregation levels — by organisation, team, and repository.

    Reuses the contributor heatmap's weighting/windowing/bot-exclusion.
    """
    contributor_heatmap = build_activity_heatmap_dataframe(records, role_lookup)
    org_heatmap = build_org_activity_heatmap(contributor_heatmap, affiliations)
    save_dataframe(org_heatmap, org_data_dir / "org_activity_heatmap.csv")
    save_dataframe(
        build_team_activity_heatmap(contributor_heatmap, team_membership), org_data_dir / "team_activity_heatmap.csv"
    )
    save_dataframe(build_repo_activity_heatmap(records), org_data_dir / "repo_activity_heatmap.csv")
    logger.info("Activity heatmaps: %d organisations, plus team and repository views", len(org_heatmap))


def _write_activity_views(role_lookup, team_membership, affiliations, org_data_dir, *, org: str = ORG):
    """Activity-driven views: the per-org/team/repo activity heatmaps.

    Nothing else here is windowed: the diversity tables are deliberately not
    time-filterable (diversity is a roster property, and windowing it mostly
    re-measures activity, which the activity views already show). Loads the
    (cached) org activity dataset once; skips quietly if no activity data is
    available.
    """
    client = shared_client()
    records = load_contributor_activity(client, org)
    if not records:
        logger.info("No activity data available; skipping activity heatmaps")
        return

    _write_activity_heatmaps(records, role_lookup, team_membership, affiliations, org_data_dir)


def _write_role_views(
    role,
    suffix,
    role_lookup,
    affiliations,
    manual_logins,
    data_dir,
):
    """Every org-scoped table for one governance role: reference table, distribution, mixes."""
    holders = highest_role_holders(role_lookup, role)
    plural = role_column(role)
    logger.info("Resolved %d distinct %s from governance config", len(holders), plural)

    classified = classify_role_holders(holders, affiliations)
    # Flag how each affiliation was decided: a hand-correction (marked '# manual' in
    # the YAML) vs the automated resolver.
    classified["method"] = [
        "manual" if str(login).lower() in manual_logins else "automated" for login in classified["login"]
    ]
    save_dataframe(classified, data_dir / f"{role}_affiliations.csv")

    summary = summarize_affiliation(classified)
    known_share = known_share_pct(classified)
    logger.info(
        "Affiliation coverage (%s): %d affiliated, %d independent, %d unknown of %d (%d%% known)",
        role,
        summary.affiliated,
        summary.independent,
        summary.unknown,
        summary.total,
        known_share,
    )
    if holders and known_share < AFFILIATION_MIN_KNOWN_SHARE_PCT:
        logger.warning(
            "Affiliation curation for %s has decayed to %d%% known (floor %d%%): the %s diversity tables "
            "now describe a minority of the population — resolve unknowns in %s",
            role,
            known_share,
            AFFILIATION_MIN_KNOWN_SHARE_PCT,
            role,
            AFFILIATIONS_PATH,
        )
    logger.info(
        "Concentration (%s): HHI %d across %d employers; largest is %s at %d%%",
        role,
        summary.hhi,
        summary.distinct_orgs,
        summary.top_org,
        summary.top_share_pct,
    )

    # Per-repo views read the same disjoint population as the distribution: a seat counts
    # here only when the holder has nothing more senior anywhere else.
    role_repos = highest_role_lookup(role_lookup, role)
    _write_distribution(classified, data_dir, suffix=suffix, value_col=plural)
    _write_repo_composition(role_repos, affiliations, data_dir, role=role, suffix=suffix)
    _write_repo_diversity(role_repos, affiliations, data_dir, role=role, suffix=suffix)


def main(org: str = ORG) -> None:
    """Build the organisation-diversity outputs for ``org``."""
    org_data_dir = ensure_org_dirs(org)

    config = fetch_governance_config(org)
    role_lookup = build_repo_role_lookup(config)
    team_membership = build_team_membership(config)
    affiliations = load_affiliations()
    manual_logins = load_manual_logins()

    # One set of org-scoped views per role tab. Roles are resolved at each
    # person's *highest* role anywhere, so the populations are disjoint and agree
    # with the dashboard's role metric tiles — a committer here has write access
    # and no maintainer seat, which is what makes the two tabs comparable.
    for role, suffix in ROLE_VARIANTS:
        _write_role_views(role, suffix, role_lookup, affiliations, manual_logins, org_data_dir)

    # Team views are role-agnostic (membership, not permissions), so they stay single-variant.
    _write_single_employer_teams(team_membership, affiliations, org_data_dir, suffix="")
    _write_team_composition(team_membership, affiliations, org_data_dir, suffix="")
    team_diversity = build_team_affiliation_diversity(team_membership, affiliations)
    save_dataframe(team_diversity, org_data_dir / "team_affiliation_diversity.csv")
    if not team_diversity.empty:
        logger.info(
            "Team diversity: %d of %d teams are single-employer among resolved members (capture risk)",
            int(team_diversity["single_employer"].sum()),
            len(team_diversity),
        )

    # Activity-driven views: the org/team/repo activity heatmaps.
    _write_activity_views(role_lookup, team_membership, affiliations, org_data_dir, org=org)

    logger.info("Organisation-diversity analytics complete")
