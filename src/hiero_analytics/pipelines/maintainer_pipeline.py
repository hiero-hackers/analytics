"""Run maintainer pipeline analytics for a GitHub organization."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from hiero_analytics.analysis.maintainer_pipeline import (
    RECENT_DAILY_BUCKETS,
    RECENT_MONTHLY_BUCKETS,
    RECENT_WEEKLY_BUCKETS,
    STAGE_COLUMNS,
    activity_to_role_dataframe,
    build_maintainer_daily_pipeline,
    build_maintainer_monthly_pipeline,
    build_maintainer_repo_pipeline,
    build_maintainer_weekly_pipeline,
    build_maintainer_yearly_pipeline,
    calendar_recent_buckets,
    humanize_day_label,
    humanize_month_label,
    humanize_week_label,
    last_calendar_buckets,
)
from hiero_analytics.config.charts import MAINTAINER_PIPELINE_COLORS
from hiero_analytics.config.paths import ORG
from hiero_analytics.data_sources.governance_config import build_repo_role_lookup, fetch_governance_config
from hiero_analytics.domain.periods import ACTIVITY_PERIODS
from hiero_analytics.export.save import plot_and_save, save_dataframe
from hiero_analytics.pipelines._shared import load_contributor_activity, org_context
from hiero_analytics.plotting.bars import plot_stacked_bar

STACK_LABELS = ["General User", "Triage", "Committer", "Maintainer"]


logger = logging.getLogger(__name__)


def main(org: str = ORG) -> None:
    """Run maintainer pipeline analytics for the configured organization."""
    client, org_data_dir, org_charts_dir = org_context(org)

    logger.info("Running maintainer pipeline analytics for org: %s", org)

    gov_config = fetch_governance_config(org)
    repo_role_lookup = build_repo_role_lookup(gov_config)

    records = load_contributor_activity(client, org)

    logger.info("Fetched %d contributor activity records", len(records))

    stage_df = activity_to_role_dataframe(records, repo_role_lookup)
    yearly_pipeline = build_maintainer_yearly_pipeline(stage_df)
    daily_pipeline = build_maintainer_daily_pipeline(stage_df)
    monthly_pipeline = build_maintainer_monthly_pipeline(stage_df)
    weekly_pipeline = build_maintainer_weekly_pipeline(stage_df)

    save_dataframe(stage_df, org_data_dir / "maintainer_activity_events.csv")
    save_dataframe(yearly_pipeline, org_data_dir / "maintainer_pipeline_yearly.csv")
    save_dataframe(daily_pipeline, org_data_dir / "maintainer_pipeline_daily.csv")
    save_dataframe(monthly_pipeline, org_data_dir / "maintainer_pipeline_monthly.csv")
    save_dataframe(weekly_pipeline, org_data_dir / "maintainer_pipeline_weekly.csv")

    logger.info("Saved maintainer pipeline tables")

    # One clock for every chart window, so the daily/weekly/monthly views agree
    # on what "now" is. The windows are complete calendar spans (zero buckets
    # included), not the last N buckets that happened to have activity.
    now = datetime.now(UTC)

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
        calendar_recent_buckets(daily_pipeline, last_calendar_buckets(now, RECENT_DAILY_BUCKETS, "day")).assign(
            day=lambda frame: frame["day"].map(humanize_day_label)
        ),
        plot_stacked_bar,
        output_path=org_charts_dir / "maintainer_pipeline_daily.png",
        x_col="day",
        stack_cols=STAGE_COLUMNS,
        labels=STACK_LABELS,
        colors=MAINTAINER_PIPELINE_COLORS,
        title=(
            "Maintainer Pipeline: Unique Active Contributors by Role - PR & Issue Activity "
            f"(Daily, last {RECENT_DAILY_BUCKETS} days)"
        ),
        rotate_x=45,
        annotate_totals=True,
        # Time series: keep chronological order. The default magnitude sort
        # treats the 'YYYY-MM-DD' labels as categorical and reorders the week
        # into a descending ranking, which reads as a trend that isn't there.
        sort_categorical=False,
    )

    plot_and_save(
        calendar_recent_buckets(monthly_pipeline, last_calendar_buckets(now, RECENT_MONTHLY_BUCKETS, "month")).assign(
            month=lambda frame: frame["month"].map(humanize_month_label)
        ),
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
        annotate_totals=True,
        # Time series: keep chronological order, oldest first, so time reads
        # forward (top to bottom when horizontal). The default magnitude sort
        # would treat the string labels as categorical and shuffle the
        # timeline. Horizontal keeps the legend clear of the month labels.
        sort_categorical=False,
        force_horizontal=True,
    )

    plot_and_save(
        calendar_recent_buckets(weekly_pipeline, last_calendar_buckets(now, RECENT_WEEKLY_BUCKETS, "week")).assign(
            week=lambda frame: frame["week"].map(humanize_week_label)
        ),
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
        annotate_totals=True,
        # Time series: chronological, oldest first — time reads forward.
        # Horizontal keeps the legend clear of the labels.
        sort_categorical=False,
        force_horizontal=True,
    )

    # The by-repository card: the same spans as the over-time card (all time,
    # 1 year, 1 month, week), so the two never offer different windows for the
    # same idea. All-time keeps the unsuffixed filename.
    repo_spans = [("All time", None, "")] + [
        (period.label, period.days, f"_{period.key}") for period in reversed(ACTIVITY_PERIODS)
    ]
    for span_label, span_days, suffix in repo_spans:
        repo_pipeline = build_maintainer_repo_pipeline(stage_df, active_window_days=span_days)
        save_dataframe(repo_pipeline, org_data_dir / f"maintainer_pipeline_by_repo{suffix}.csv")
        plot_and_save(
            repo_pipeline,
            plot_stacked_bar,
            output_path=org_charts_dir / f"maintainer_pipeline_by_repo{suffix}.png",
            x_col="repo",
            stack_cols=STAGE_COLUMNS,
            labels=STACK_LABELS,
            colors=MAINTAINER_PIPELINE_COLORS,
            title=(
                "Maintainer Pipeline: Unique Active Contributors by Role - "
                f"PR & Issue Activity (by Repository, {span_label.lower()})"
            ),
            rotate_x=45,
            annotate_totals=True,
            legend_inside_bottom_right=True,
            auto_height_for_horizontal=False,
        )

    logger.info("Maintainer pipeline analytics complete")
