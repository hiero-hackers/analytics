"""Time-series helpers for cumulative and historical issue-difficulty trends."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from hiero_analytics.analysis.timeseries_utils import (
    DIFFICULTY_OVER_TIME_COLUMN_ORDER as _DIFFICULTY_OVER_TIME_COLUMN_ORDER,
)
from hiero_analytics.analysis.timeseries_utils import (
    difficulty_key,
    difficulty_key_for_label,
    init_row_for_sample,
    normalize_datetime,
    timeline_events_by_issue,
    weekly_sample_points,
)
from hiero_analytics.data_sources.models import IssueRecord, IssueTimelineEventRecord

TIMELINE_EVENT_ORDER = {
    "unlabeled": 0,
    "labeled": 1,
    "closed": 2,
    "reopened": 3,
}
# Re-export column order for consumers expecting it from this module.
DIFFICULTY_OVER_TIME_COLUMN_ORDER = _DIFFICULTY_OVER_TIME_COLUMN_ORDER


def get_difficulty_over_time_event_based(
    issues: list[IssueRecord],
    timeline_events: list[IssueTimelineEventRecord],
    *,
    start_at: datetime,
    today: datetime | None = None,
) -> list[dict[str, str | int]]:
    """
    Build weekly open-issue counts using only event-based forward tracking.

    Rules:
    - Only include issues created within the observation window.
    - Use the label application date (most recent labeled event) as the entry point.
    - Track forward only from the label event to the end of the window.
    - Exclude issues with no difficulty label event in the timeline.

    This approach avoids reconstructing historical state or mixing present-day
    snapshot data with historical events. Every data point is grounded in a
    recorded event.
    """
    if not issues:
        return []

    end_at = normalize_datetime(today) or datetime.now(UTC)
    start_at = normalize_datetime(start_at) or end_at

    if end_at < start_at:
        end_at = start_at

    # Normalize sample points to midnight UTC for calendar-aligned buckets.
    start_at = start_at.replace(hour=0, minute=0, second=0, microsecond=0)
    end_at = end_at.replace(hour=0, minute=0, second=0, microsecond=0)

    # Filter: only issues created within the window.
    filtered_issues = [
        issue
        for issue in issues
        if (created := normalize_datetime(issue.created_at)) is not None and start_at <= created <= end_at
    ]

    if not filtered_issues:
        return []

    # Group events by issue.
    events_by_issue = timeline_events_by_issue(
        timeline_events,
        event_type_order=TIMELINE_EVENT_ORDER,
    )

    # For each issue, find the most recent labeled event for its current difficulty.
    issue_entry_points: dict[tuple[str, int], tuple[str, datetime]] = {}

    for issue in filtered_issues:
        current_difficulty = difficulty_key(set(issue.labels or []))
        if current_difficulty is None:
            # Skip issues with no current difficulty label.
            continue

        issue_events = events_by_issue.get((issue.repo, issue.number), [])

        # Find the most recent labeled event for this difficulty.
        most_recent_label_event: IssueTimelineEventRecord | None = None
        for event in reversed(issue_events):
            if event.event_type == "labeled" and difficulty_key_for_label(event.label) == current_difficulty:
                most_recent_label_event = event
                break

        if most_recent_label_event is None:
            # Skip issues with no recorded label event.
            continue

        label_timestamp = normalize_datetime(most_recent_label_event.occurred_at)
        if label_timestamp is None:
            continue

        # Only track from the label event onward; skip if label event is after window.
        if label_timestamp > end_at:
            continue

        issue_entry_points[(issue.repo, issue.number)] = (current_difficulty, label_timestamp)

    if not issue_entry_points:
        return []

    issues_by_key = {(issue.repo, issue.number): issue for issue in filtered_issues}

    # Build sample points.
    sample_points = weekly_sample_points(start_at, end_at)

    # Generate weekly rows.
    series: list[dict[str, str | int]] = []

    for sample_point in sample_points:
        row = init_row_for_sample(sample_point)

        for (repo, number), (bucket, label_timestamp) in issue_entry_points.items():
            issue = issues_by_key.get((repo, number))
            if issue is None:
                continue

            # Issue enters the dataset at its label event.
            if sample_point < label_timestamp:
                continue

            # Issue is open if no closed_at or closed_at is after the sample point.
            closed_at = normalize_datetime(issue.closed_at)
            if closed_at is not None and closed_at <= sample_point:
                continue

            row[bucket] += 1

        series.append(row)

    return series


def cumulative_timeseries(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    """
    Build a cumulative count series over time.

    Parameters
    ----------
    df
        Input dataframe containing a datetime column.
    date_col
        Name of the datetime column to use for the timeline.

    Returns:
    -------
    pd.DataFrame
        Dataframe with:
        - ``date_col``: timeline values
        - ``count``: cumulative count
    """
    if df.empty:
        return pd.DataFrame(columns=[date_col, "count"])

    out = df[[date_col]].dropna().sort_values(date_col).assign(count=1)

    out["count"] = out["count"].cumsum()

    return out.reset_index(drop=True)
