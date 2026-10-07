"""Run maintainer pipeline analytics for a GitHub organization."""

from __future__ import annotations

import logging

from hiero_analytics.analysis.maintainer_pipeline import (
    activity_to_role_dataframe,
    build_maintainer_daily_pipeline,
    build_maintainer_monthly_pipeline,
    build_maintainer_repo_pipeline,
    build_maintainer_weekly_pipeline,
    build_maintainer_yearly_pipeline,
)
from hiero_analytics.config.paths import ORG
from hiero_analytics.data_sources.governance_config import build_repo_role_lookup, fetch_governance_config
from hiero_analytics.domain.periods import ACTIVITY_PERIODS
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.pipelines._shared import load_contributor_activity, org_context

logger = logging.getLogger(__name__)


def main(org: str = ORG) -> None:
    """Run maintainer pipeline analytics for the configured organization."""
    client, org_data_dir = org_context(org)

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

    # The by-repository card: the same spans as the over-time card (all time,
    # 1 year, 1 month, week), so the two never offer different windows for the
    # same idea. All-time keeps the unsuffixed filename.
    repo_spans = [(None, "")] + [(period.days, f"_{period.key}") for period in reversed(ACTIVITY_PERIODS)]
    for span_days, suffix in repo_spans:
        repo_pipeline = build_maintainer_repo_pipeline(stage_df, active_window_days=span_days)
        save_dataframe(repo_pipeline, org_data_dir / f"maintainer_pipeline_by_repo{suffix}.csv")

    logger.info("Maintainer pipeline analytics complete")
