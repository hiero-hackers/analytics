"""Release cadence and staleness pipeline.

Network-only pipeline with `extra_orgs=True`; skipped during offline runs.
Publishes standalone release timeline and staleness artifacts rather than
joining the governance-dependent `repo_activity_overview`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from hiero_analytics.analysis.releases import build_release_staleness, build_release_timeline
from hiero_analytics.config.paths import ORG
from hiero_analytics.data_sources.github_ingest import fetch_org_releases_graphql, fetch_org_repos_graphql
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.pipelines._shared import org_context
from hiero_analytics.plotting.bars import plot_bar
from hiero_analytics.plotting.scatter import plot_release_timeline

logger = logging.getLogger(__name__)

# The dot timeline windows to roughly the last 18 months at chart time — the
# CSV artifact keeps full history regardless (see build_release_timeline).
TIMELINE_WINDOW_DAYS = 548

# Matches the hiero_hackers.py "Top 20" bar-chart convention for a
# potentially-long per-repo list.
STALENESS_CHART_TOP_N = 20


def main(org: str = ORG):
    """Fetch releases for every repo in the org and publish the timeline/staleness tables + charts."""
    client, org_data_dir, org_charts_dir = org_context(org)

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

    windowed = timeline[timeline["published_at"] >= datetime.now(UTC) - timedelta(days=TIMELINE_WINDOW_DAYS)]
    if not windowed.empty:
        plot_release_timeline(
            windowed,
            title="Release timeline (last ~18 months)",
            output_path=org_charts_dir / "release_timeline.png",
        )

    # Repos with no established cadence (fewer than two releases ever, or a
    # zero-day median gap) have a null ratio and are correctly excluded here
    # rather than shown as unranked — see analysis/releases.py.
    overdue = staleness.dropna(subset=["staleness_ratio"]).sort_values("staleness_ratio", ascending=False)
    if not overdue.empty:
        plot_bar(
            df=overdue.head(STALENESS_CHART_TOP_N),
            x_col="repo",
            y_col="staleness_ratio",
            title=f"Top {STALENESS_CHART_TOP_N} most overdue vs. own release cadence",
            output_path=org_charts_dir / "release_staleness.png",
        )
