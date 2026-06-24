"""
Hiero Hackers GitHub organization analytics runner.

Generates charts that summarize the activity and composition of the
hiero-hackers GitHub organization:

- Repository push activity (active vs inactive)
- Programming language distribution
- Contributor counts per repository

Charts are written to ``outputs/charts/org/hiero-hackers/``.
"""

from __future__ import annotations

import logging

from hiero_analytics.analysis.hiero_hackers_analysis import (
    build_contributor_counts,
    calculate_language_distribution,
    calculate_push_activity_summary,
    repos_to_dataframe,
)
from hiero_analytics.config.paths import ensure_org_dirs
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import (
    fetch_org_contributor_activity_graphql,
    fetch_org_repos_graphql,
)
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.plotting.bars import plot_bar
from hiero_analytics.plotting.pie import plot_pie

ORG = "hiero-hackers"

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def main() -> None:
    """Generate the Hiero Hackers organization chart bundle."""
    # Initialize GitHub API client
    client = GitHubClient()
    
    # Create output directories
    data_dir, charts_dir = ensure_org_dirs(ORG)
    
    # Fetch data from GitHub API
    repo_records = fetch_org_repos_graphql(client, ORG)
    activity_records = fetch_org_contributor_activity_graphql(client, ORG)
    
    # Transform to DataFrames
    repos_df = repos_to_dataframe(repo_records)
    
    # Generate language distribution chart and CSV (only if data exists)
    language_df = calculate_language_distribution(repos_df)
    if not language_df.empty:
        plot_bar(
            df=language_df,
            x_col="language",
            y_col="count",
            title="Hiero Hackers — Programming Languages",
            output_path=charts_dir / "language_distribution.png",
        )
        save_dataframe(language_df, data_dir / "language_distribution.csv")
    
    # Generate push activity summary chart and CSV (only if data has non-zero values)
    activity_df = calculate_push_activity_summary(repos_df, days=30)
    if not activity_df.empty and activity_df["count"].sum() > 0:
        plot_pie(
            df=activity_df,
            label_col="status",
            value_col="count",
            title="Hiero Hackers — Repository Push Activity (Last 30 Days)",
            output_path=charts_dir / "push_activity.png",
        )
        save_dataframe(activity_df, data_dir / "push_activity.csv")
    
    # Generate contributor counts chart and CSV (only if data exists)
    contributors_df = build_contributor_counts(activity_records)
    if not contributors_df.empty:
        contributors_df = contributors_df.sort_values("contributors", ascending=False).head(20)
        plot_bar(
            df=contributors_df,
            x_col="repo",
            y_col="contributors",
            title="Hiero Hackers — Top 20 Repositories by Contributors",
            output_path=charts_dir / "contributor_counts.png",
        )
        save_dataframe(contributors_df, data_dir / "contributor_counts.csv")
    
    logger.info("Hiero Hackers analytics complete. Charts written to %s", charts_dir)


if __name__ == "__main__":
    main()
