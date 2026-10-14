"""Org overview — the composition-level cards for an organization.

Orchestration only, mirroring ``contributor_heatmap``: it builds the org-wide
cards (repositories ranked by contributor count, language mix, recent pushes)
for every org the registry marks ``org_overview``. Parameterised on the org, so
registering another composition org in ``config/orgs.py`` gains it these cards
with no new pipeline.

Tables are written to ``outputs/data/org/<org>/``.
"""

from __future__ import annotations

import logging

from hiero_analytics.analysis.org_overview_analysis import (
    build_contributor_counts,
    calculate_language_distribution,
    calculate_push_activity_summary,
    repos_to_dataframe,
)
from hiero_analytics.config.orgs import ORGS
from hiero_analytics.data_sources.github_ingest import (
    fetch_org_contributor_activity_graphql,
    fetch_org_repos_graphql,
)
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.pipelines._shared import org_context, shared_client

logger = logging.getLogger(__name__)


def _build_org_overview(org: str) -> None:
    """Build the org-wide composition cards for one org."""
    client, data_dir = org_context(org)

    repo_records = fetch_org_repos_graphql(client, org)
    activity_records = fetch_org_contributor_activity_graphql(client, org)

    repos_df = repos_to_dataframe(repo_records)

    # Language distribution, only when the org has repos to describe.
    language_df = calculate_language_distribution(repos_df)
    if not language_df.empty:
        save_dataframe(language_df, data_dir / "language_distribution.csv")

    # Push activity, only when the values are non-zero
    activity_df = calculate_push_activity_summary(repos_df, days=30)
    if not activity_df.empty and activity_df["count"].sum() > 0:
        save_dataframe(activity_df, data_dir / "push_activity.csv")

    contributors_df = build_contributor_counts(activity_records)
    if not contributors_df.empty:
        contributors_df = contributors_df.sort_values("contributors", ascending=False)
        save_dataframe(contributors_df, data_dir / "contributor_counts.csv")

    logger.info("Org overview complete for %s. Tables written to %s", org, data_dir)


def main(org: str | None = None) -> None:
    """Build the org-overview cards for ``org``, or every org-overview org.

    Without an org argument it iterates the registry, so one invocation covers
    every composition org; with one it builds just that org (the CLI's ``--org``).
    """
    shared_client()
    targets = [org] if org else [profile.name for profile in ORGS if profile.org_overview]
    for target in targets:
        _build_org_overview(target)
