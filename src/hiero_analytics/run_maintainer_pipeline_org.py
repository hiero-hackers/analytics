"""Run maintainer pipeline analytics for a GitHub organization."""

from __future__ import annotations

import logging

from hiero_analytics.analysis.maintainer_pipeline import (
    RECENT_MONTHLY_BUCKETS,
    RECENT_WEEKLY_BUCKETS,
    STAGE_COLUMNS,
    activity_to_role_dataframe,
    build_maintainer_monthly_pipeline,
    build_maintainer_repo_pipeline,
    build_maintainer_weekly_pipeline,
    build_maintainer_yearly_pipeline,
    recent_buckets,
)
from hiero_analytics.config.charts import MAINTAINER_PIPELINE_COLORS
from hiero_analytics.config.logging_config import setup_logging
from hiero_analytics.config.paths import ORG, ensure_org_dirs
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import fetch_org_contributor_activity_graphql
from hiero_analytics.data_sources.governance_config import build_repo_role_lookup, fetch_governance_config
from hiero_analytics.export.save import plot_and_save, save_dataframe
from hiero_analytics.plotting.bars import plot_stacked_bar

STACK_LABELS = ["General User", "Triage", "Committer", "Maintainer"]


logger = logging.getLogger(__name__)


def main(org: str | None = None) -> None:
    """Run maintainer pipeline analytics for the configured organization."""
    resolved_org = org or ORG

    org_data_dir, org_charts_dir = ensure_org_dirs(resolved_org)

    logger.info("Running maintainer pipeline analytics for org: %s", resolved_org)

    gov_config = fetch_governance_config()
    repo_role_lookup = build_repo_role_lookup(gov_config)

    client = GitHubClient()
    records = fetch_org_contributor_activity_graphql(client, org=resolved_org, lookback_days=None)

    logger.info("Fetched %d contributor activity records", len(records))

    stage_df = activity_to_role_dataframe(records, repo_role_lookup)
    yearly_pipeline = build_maintainer_yearly_pipeline(stage_df)
    monthly_pipeline = build_maintainer_monthly_pipeline(stage_df)
    weekly_pipeline = build_maintainer_weekly_pipeline(stage_df)
    repo_pipeline = build_maintainer_repo_pipeline(stage_df)

    save_dataframe(stage_df, org_data_dir / "maintainer_activity_events.csv")
    save_dataframe(yearly_pipeline, org_data_dir / "maintainer_pipeline_yearly.csv")
    save_dataframe(monthly_pipeline, org_data_dir / "maintainer_pipeline_monthly.csv")
    save_dataframe(weekly_pipeline, org_data_dir / "maintainer_pipeline_weekly.csv")
    save_dataframe(repo_pipeline, org_data_dir / "maintainer_pipeline_by_repo.csv")

    logger.info("Saved maintainer pipeline tables")

    plot_and_save(
        yearly_pipeline,
        plot_stacked_bar,
        output_path=org_charts_dir / "maintainer_pipeline_yearly.png",
        x_col="year",
        stack_cols=STAGE_COLUMNS,
        labels=STACK_LABELS,
        colors=MAINTAINER_PIPELINE_COLORS,
        title="Maintainer Pipeline: Unique Active Contributors by Role - PR & Issue Activity (Yearly)",
        annotate_totals=True,
    )

    plot_and_save(
        recent_buckets(monthly_pipeline, RECENT_MONTHLY_BUCKETS, newest_first=True),
        plot_stacked_bar,
        output_path=org_charts_dir / "maintainer_pipeline_monthly.png",
        x_col="month",
        stack_cols=STAGE_COLUMNS,
        labels=STACK_LABELS,
        colors=MAINTAINER_PIPELINE_COLORS,
        title=(
            "Maintainer Pipeline: Unique Active Contributors by Role - PR & Issue Activity "
            f"(Monthly, last {RECENT_MONTHLY_BUCKETS} months)"
        ),
        rotate_x=45,
        annotate_totals=False,
        # Time series: keep chronological order (newest at top) rather than the
        # default magnitude sort, which would otherwise treat the string
        # 'YYYY-MM' labels as categorical and shuffle the timeline. Horizontal
        # keeps the legend clear of the month labels.
        sort_categorical=False,
        force_horizontal=True,
    )

    plot_and_save(
        recent_buckets(weekly_pipeline, RECENT_WEEKLY_BUCKETS, newest_first=True),
        plot_stacked_bar,
        output_path=org_charts_dir / "maintainer_pipeline_weekly.png",
        x_col="week",
        stack_cols=STAGE_COLUMNS,
        labels=STACK_LABELS,
        colors=MAINTAINER_PIPELINE_COLORS,
        title=(
            "Maintainer Pipeline: Unique Active Contributors by Role - PR & Issue Activity "
            f"(Weekly, last {RECENT_WEEKLY_BUCKETS} weeks)"
        ),
        rotate_x=45,
        annotate_totals=False,
        # Time series: keep chronological order (newest at top) instead of the
        # default magnitude sort. Horizontal keeps the legend clear of the labels.
        sort_categorical=False,
        force_horizontal=True,
    )

    plot_and_save(
        repo_pipeline,
        plot_stacked_bar,
        output_path=org_charts_dir / "maintainer_pipeline_by_repo.png",
        x_col="repo",
        stack_cols=STAGE_COLUMNS,
        labels=STACK_LABELS,
        colors=MAINTAINER_PIPELINE_COLORS,
        title="Maintainer Pipeline: Unique Active Contributors by Role - PR & Issue Activity (by Repository)",
        rotate_x=45,
        annotate_totals=False,
        legend_inside_bottom_right=True,
        auto_height_for_horizontal=False,
    )

    logger.info("Maintainer pipeline analytics complete")


if __name__ == "__main__":
    setup_logging()
    main()
