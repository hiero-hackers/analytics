"""Repo-growth timeline pipeline.

Generates a "repos created per month" line chart and a "cumulative repos over
time" line chart from the ``createdAt`` metadata that the repos GraphQL query
already returns.  Zero-config: no extra token, no audit-log access, all-time
coverage.

Charts are written to ``outputs/charts/org/<org>/``.

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
from hiero_analytics.plotting.lines import plot_date_line

logger = logging.getLogger(__name__)


def main(org: str = ORG) -> None:
    """Generate repos-over-time charts for *org*."""
    client, data_dir, charts_dir = org_context(org)

    try:
        repo_records = fetch_org_repos_graphql(client, org)
    except Exception:
        logger.warning("Could not fetch org repos for %s; skipping repo-growth charts", org)
        return

    timeline = build_repo_growth_timeline(repo_records)

    if timeline.empty:
        logger.info("No repo creation dates available for %s; skipping repo-growth charts", org)
        return

    # Scale month tick interval based on timeline length so multi-year spans stay legible.
    # ~15-20 tick labels maximum across the x-axis.
    month_interval = max(2, len(timeline) // 15)

    # --- Repos created per month ---
    plot_date_line(
        df=timeline,
        x_col="month",
        y_col="repos_created",
        title=f"{org} — Repos Created per Month",
        output_path=charts_dir / "repos_created_per_month.png",
        month_interval=month_interval,
        xlabel="Month",
        ylabel="Repos Created",
    )

    # --- Cumulative repo count ---
    plot_date_line(
        df=timeline,
        x_col="month",
        y_col="cumulative_repos",
        title=f"{org} — Cumulative Repository Count",
        output_path=charts_dir / "cumulative_repo_count.png",
        month_interval=month_interval,
        xlabel="Month",
        ylabel="Cumulative Repos",
    )

    save_dataframe(timeline, data_dir / "repo_growth_timeline.csv")
    logger.info("Repo-growth charts written to %s", charts_dir)
