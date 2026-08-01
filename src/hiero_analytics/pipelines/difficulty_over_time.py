"""Run event-based difficulty-over-time analytics for an organization."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from hiero_analytics.analysis.timeseries import (
    DIFFICULTY_OVER_TIME_ALL_COLUMN_ORDER,
    DIFFICULTY_OVER_TIME_COLUMN_ORDER,
    get_difficulty_over_time_event_based,
)
from hiero_analytics.config.analysis import DIFFICULTY_OVER_TIME_WINDOW_DAYS, TIMELINE_MAX_WORKERS
from hiero_analytics.config.charts import DIFFICULTY_COLORS
from hiero_analytics.config.paths import ORG
from hiero_analytics.data_sources.github_ingest import (
    fetch_org_issue_label_events_graphql,
    fetch_org_issues_graphql,
)
from hiero_analytics.domain.labels import (
    DIFFICULTY_ADVANCED,
    DIFFICULTY_BEGINNER,
    DIFFICULTY_GOOD_FIRST_ISSUE,
    DIFFICULTY_INTERMEDIATE,
    UNKNOWN_DIFFICULTY,
)
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.pipelines._shared import org_context
from hiero_analytics.plotting.lines import plot_stacked_area

DIFFICULTY_OVER_TIME_LABELS = [
    DIFFICULTY_GOOD_FIRST_ISSUE.name,
    DIFFICULTY_BEGINNER.name,
    DIFFICULTY_INTERMEDIATE.name,
    DIFFICULTY_ADVANCED.name,
]

DIFFICULTY_OVER_TIME_ALL_LABELS = [
    UNKNOWN_DIFFICULTY,
    *DIFFICULTY_OVER_TIME_LABELS,
]


logger = logging.getLogger(__name__)


def _export_series(
    series: list[dict[str, str | int]],
    *,
    columns: list[str],
    labels: list[str],
    stem: str,
    title: str,
    org_data_dir: Path,
    org_charts_dir: Path,
) -> None:
    """Save one difficulty-over-time series as a CSV plus stacked-area chart."""
    frame = pd.DataFrame(series)
    if frame.empty:
        logger.info("No difficulty-over-time data available for %s", stem)
        return

    frame = frame[["date", *columns]]

    save_dataframe(frame, org_data_dir / f"{stem}.csv")

    plot_stacked_area(
        frame,
        x_col="date",
        stack_cols=columns,
        labels=labels,
        title=title,
        output_path=org_charts_dir / f"{stem}.png",
        colors=DIFFICULTY_COLORS,
        xlabel="Date",
        ylabel="Open issues",
    )


def main(org: str = ORG) -> None:
    """Generate an org-wide event-based difficulty-over-time chart."""
    client, org_data_dir, org_charts_dir = org_context(org)
    end_at = datetime.now(UTC)
    start_at = end_at - timedelta(days=DIFFICULTY_OVER_TIME_WINDOW_DAYS)

    logger.info("Running event-based difficulty-over-time analytics for org: %s", org)
    logger.info(f"Window: {start_at.date().isoformat()} to {end_at.date().isoformat()}")

    # Fetch all issues (open and closed) to get the complete issue set.
    all_issues = fetch_org_issues_graphql(client, org=org, states=["OPEN", "CLOSED"])
    logger.info("Fetched %d total issues", len(all_issues))

    # Fetch label add/remove events (GraphQL timelineItems) to identify label
    # application dates. Only LABELED/UNLABELED events are transferred, so this
    # avoids the repo-wide REST event firehose and its 300-page truncation.
    timeline_events = fetch_org_issue_label_events_graphql(
        client,
        org=org,
        states=["OPEN", "CLOSED"],
        max_workers=TIMELINE_MAX_WORKERS,
    )
    logger.info("Fetched %d repository issue events", len(timeline_events))

    # Build event-based difficulty-over-time series: one restricted to
    # difficulty-labelled issues (as before), one adding the unknown bucket so
    # untriaged volume is visible without swamping the labelled view (#259).
    _export_series(
        get_difficulty_over_time_event_based(
            all_issues,
            timeline_events,
            start_at=start_at,
            today=end_at,
        ),
        columns=DIFFICULTY_OVER_TIME_COLUMN_ORDER,
        labels=DIFFICULTY_OVER_TIME_LABELS,
        stem="difficulty_over_time_event_based_weekly",
        title="Open Issues by Difficulty Over Time (Event-Based)",
        org_data_dir=org_data_dir,
        org_charts_dir=org_charts_dir,
    )

    _export_series(
        get_difficulty_over_time_event_based(
            all_issues,
            timeline_events,
            start_at=start_at,
            today=end_at,
            include_unknown=True,
        ),
        columns=DIFFICULTY_OVER_TIME_ALL_COLUMN_ORDER,
        labels=DIFFICULTY_OVER_TIME_ALL_LABELS,
        stem="difficulty_over_time_all_event_based_weekly",
        title="All Open Issues by Difficulty Over Time (Event-Based)",
        org_data_dir=org_data_dir,
        org_charts_dir=org_charts_dir,
    )

    logger.info("Event-based difficulty-over-time analytics complete")
