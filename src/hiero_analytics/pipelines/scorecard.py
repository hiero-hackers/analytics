"""Runner script that fetches OpenSSF Scorecard results for all repos in an organisation."""

from __future__ import annotations

import logging

import requests

from hiero_analytics.analysis.scorecard_analysis import (
    scorecard_stacked_dataframe,
    scorecard_to_dataframe,
)
from hiero_analytics.config.paths import ORG
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import fetch_org_repos_graphql
from hiero_analytics.data_sources.models import ScorecardRecord
from hiero_analytics.data_sources.scorecard import fetch_repo_scorecard
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.pipelines._shared import org_context

logger = logging.getLogger(__name__)


def fetch_org_repos(client: GitHubClient, org: str):
    """Fetch repos for the organization."""
    return fetch_org_repos_graphql(client, org)


def fetch_all_scorecards(repos, *, org: str = ORG) -> list[ScorecardRecord]:
    """Fetch scorecards for each repository in the organization.

    A transient failure is retried once; a second failure propagates, so the
    run fails loudly rather than publishing a partial scorecard chart.
    """
    scorecards: list[ScorecardRecord] = []

    for i, repo in enumerate(repos, start=1):
        logger.info("Fetching scorecard (%d/%d): %s", i, len(repos), repo.name)

        try:
            sc = fetch_repo_scorecard(repo.name, org=org)
        except requests.RequestException:
            logger.warning("Scorecard fetch failed for %s; retrying once", repo.name)
            sc = fetch_repo_scorecard(repo.name, org=org)
        if sc:
            scorecards.append(sc)

    return scorecards


def main(org: str = ORG):
    """Fetch scorecards for all organisation repos and write the score tables."""
    client, org_data_dir = org_context(org)

    repos = fetch_org_repos(client, org)

    if not repos:
        logger.warning("No repositories found for org: %s", org)
        return

    scorecards = fetch_all_scorecards(repos, org=org)

    if not scorecards:
        logger.warning("No scorecards fetched")
        return

    df = scorecard_to_dataframe(scorecards)
    save_dataframe(df, org_data_dir / "org_scorecard.csv")
    # -1 (inconclusive) is kept and unreported checks stay blank, never a zero score.
    save_dataframe(scorecard_stacked_dataframe(scorecards, missing=None), org_data_dir / "org_scorecard_checks.csv")

    logger.info("Scorecard tables written.")
