"""Runner script that fetches OpenSSF Scorecard results for all repos in an organisation."""

from __future__ import annotations

import logging

import requests

from hiero_analytics.analysis.scorecard_analysis import (
    CHECK_COLUMNS,
    scorecard_stacked_dataframe,
    scorecard_to_dataframe,
)
from hiero_analytics.config.charts import SCORECARD_CHECK_COLORS
from hiero_analytics.config.paths import ORG
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import fetch_org_repos_graphql
from hiero_analytics.data_sources.models import ScorecardRecord
from hiero_analytics.data_sources.scorecard import fetch_repo_scorecard
from hiero_analytics.export.save import plot_and_save
from hiero_analytics.pipelines._shared import org_context
from hiero_analytics.plotting.bars import plot_bar, plot_stacked_bar

logger = logging.getLogger(__name__)


def fetch_org_repos(client: GitHubClient, org: str):
    """Fetch repos for the organization."""
    return fetch_org_repos_graphql(client, org)


def fetch_all_scorecards(repos) -> list[ScorecardRecord]:
    """Fetch scorecards for each repository in the organization.

    A transient failure is retried once; a second failure propagates, so the
    run fails loudly rather than publishing a partial scorecard chart.
    """
    scorecards: list[ScorecardRecord] = []

    for i, repo in enumerate(repos, start=1):
        logger.info("Fetching scorecard (%d/%d): %s", i, len(repos), repo.name)

        try:
            sc = fetch_repo_scorecard(repo.name)
        except requests.RequestException:
            logger.warning("Scorecard fetch failed for %s; retrying once", repo.name)
            sc = fetch_repo_scorecard(repo.name)
        if sc:
            scorecards.append(sc)

    return scorecards


def main(org: str = ORG):
    """Fetch scorecards for all organisation repos and generate bar charts."""
    client, _, org_charts_dir = org_context(org)

    repos = fetch_org_repos(client, org)

    if not repos:
        logger.warning("No repositories found for org: %s", org)
        return

    scorecards = fetch_all_scorecards(repos)

    if not scorecards:
        logger.warning("No scorecards fetched")
        return

    df = scorecard_to_dataframe(scorecards)
    plot_and_save(
        df,
        plot_bar,
        output_path=org_charts_dir / "org_scorecard.png",
        x_col="repo",
        y_col="score",
        title="OpenSSF Scores by Repository",
    )

    df_stacked = scorecard_stacked_dataframe(scorecards)
    plot_and_save(
        df_stacked,
        plot_stacked_bar,
        output_path=org_charts_dir / "org_scorecard_breakdown.png",
        x_col="repo",
        stack_cols=CHECK_COLUMNS,
        labels=CHECK_COLUMNS,
        colors=SCORECARD_CHECK_COLORS,
        title="OpenSSF Score Breakdown by Check",
        annotate_totals=False,
        rotate_x=45,
    )

    logger.info("Charts generated successfully.")
