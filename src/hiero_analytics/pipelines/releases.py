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
from hiero_analytics.domain.periods import ACTIVITY_PERIODS
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.pipelines._shared import org_context
from hiero_analytics.plotting.scatter import plot_release_timeline

logger = logging.getLogger(__name__)

# The dot timeline's all-time span, for orgs whose full history exceeds this
# (~18 months) — kept as a sane upper bound rather than plotting a decade
# of releases on one chart. Real period-tab spans (week/month/year) come
# from ACTIVITY_PERIODS below and are unaffected by this cap.
ALL_TIME_WINDOW_DAYS = 548


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

    # Period-tabbed chart spans, matching the same "All time / 1 year /
    # 1 month / Week" vocabulary every other period-tabbed chart in the
    # dashboard uses (ACTIVITY_PERIODS) — a reader shouldn't have to learn a
    # different set of windows for this one tab. "All time" caps at
    # ALL_TIME_WINDOW_DAYS rather than truly all history, both for legibility
    # and because build_release_timeline's CSV already has the full record.
    now = datetime.now(UTC)
    spans = [("All time", ALL_TIME_WINDOW_DAYS, "")] + [
        (period.label, period.days, f"_{period.key}") for period in reversed(ACTIVITY_PERIODS)
    ]
    for span_label, span_days, suffix in spans:
        windowed = timeline[timeline["published_at"] >= now - timedelta(days=span_days)]
        if windowed.empty:
            continue
        plot_release_timeline(
            windowed,
            title=f"Release timeline ({span_label.lower()})",
            output_path=org_charts_dir / f"release_timeline{suffix}.png",
        )
