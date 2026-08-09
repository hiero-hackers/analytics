"""Release cadence and staleness pipeline.

Network-only pipeline with `extra_orgs=True`; skipped during offline runs.
Publishes standalone release timeline and staleness artifacts rather than
joining the governance-dependent `repo_activity_overview`.
"""

from __future__ import annotations

import logging

from hiero_analytics.analysis.releases import build_release_staleness, build_release_timeline
from hiero_analytics.config.paths import ORG
from hiero_analytics.data_sources.github_ingest import fetch_org_releases_graphql, fetch_org_repos_graphql
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.pipelines._shared import org_context

logger = logging.getLogger(__name__)


def main(org: str = ORG):
    """Fetch releases for every repo in the org and publish the timeline/staleness tables."""
    client, org_data_dir, _org_charts_dir = org_context(org)

    all_repos = fetch_org_repos_graphql(client, org)
    if not all_repos:
        logger.warning("No repositories found for org: %s", org)
        return

    records = fetch_org_releases_graphql(client, org)

    timeline = build_release_timeline(records)
    save_dataframe(timeline, org_data_dir / "release_timeline.csv")

    staleness = build_release_staleness(records, all_repos)
    save_dataframe(staleness, org_data_dir / "release_repo_summary.csv")

    logger.info(
        "Releases pipeline complete for %s: %d releases across %d repos (%d never released).",
        org,
        len(records),
        len(all_repos),
        int(staleness["latest_release"].isna().sum()) if not staleness.empty else len(all_repos),
    )
