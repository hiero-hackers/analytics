"""
Hiero Hackers GitHub organization analytics runner.

Generates tables that summarize the activity and composition of the
hiero-hackers GitHub organization:

- Repository push activity (active vs inactive)
- Programming language distribution
- Contributor counts per repository

Tables are written to ``outputs/data/org/hiero-hackers/``.
"""

from __future__ import annotations

import logging

from hiero_analytics.analysis.hiero_hackers_analysis import (
    build_contributor_counts,
    calculate_language_distribution,
    calculate_push_activity_summary,
    repos_to_dataframe,
)
from hiero_analytics.data_sources.github_ingest import (
    fetch_org_contributor_activity_graphql,
    fetch_org_repos_graphql,
)
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.pipelines._shared import org_context

ORG = "hiero-hackers"


logger = logging.getLogger(__name__)


def main(org: str = ORG) -> None:
    """Generate the Hiero Hackers organization tables."""
    client, data_dir = org_context(org)

    # Fetch data from GitHub API
    repo_records = fetch_org_repos_graphql(client, org)
    activity_records = fetch_org_contributor_activity_graphql(client, org)

    # Transform to DataFrames
    repos_df = repos_to_dataframe(repo_records)

    # Generate language distribution CSV (only if data exists)
    language_df = calculate_language_distribution(repos_df)
    if not language_df.empty:
        save_dataframe(language_df, data_dir / "language_distribution.csv")

    # Generate push activity summary CSV (only if data has non-zero values)
    activity_df = calculate_push_activity_summary(repos_df, days=30)
    if not activity_df.empty and activity_df["count"].sum() > 0:
        save_dataframe(activity_df, data_dir / "push_activity.csv")

    # Generate contributor counts CSV (only if data exists)
    contributors_df = build_contributor_counts(activity_records)
    if not contributors_df.empty:
        contributors_df = contributors_df.sort_values("contributors", ascending=False)
        save_dataframe(contributors_df, data_dir / "contributor_counts.csv")

    logger.info("Hiero Hackers analytics complete. Tables written to %s", data_dir)
