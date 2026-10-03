"""Repo-growth timeline pipeline.

Generates the repos-created-per-month and cumulative-repos timeline table from
the ``createdAt`` metadata that the repos GraphQL query already returns.  Zero-config: no extra token, no audit-log access, all-time
coverage.

The table is written to ``outputs/data/org/<org>/repo_growth_timeline.csv``.

Addresses `hiero-hackers/analytics#283
<https://github.com/hiero-hackers/analytics/issues/283>`_.
"""

from __future__ import annotations

import logging

from hiero_analytics.analysis.repo_growth import build_repo_growth_timeline
from hiero_analytics.config.paths import ORG
from hiero_analytics.data_sources.github_ingest import fetch_org_repos_graphql
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.pipelines._shared import org_context

logger = logging.getLogger(__name__)


def main(org: str = ORG) -> None:
    """Generate repos-over-time timeline for *org*."""
    client, data_dir = org_context(org)

    try:
        repo_records = fetch_org_repos_graphql(client, org)
    except Exception:
        logger.warning("Could not fetch org repos for %s; skipping repo-growth timeline", org)
        return

    timeline = build_repo_growth_timeline(repo_records)

    if timeline.empty:
        logger.info("No repo creation dates available for %s; skipping repo-growth timeline", org)
        return

    save_dataframe(timeline, data_dir / "repo_growth_timeline.csv")
    logger.info("Repo-growth timeline written to %s", data_dir)
