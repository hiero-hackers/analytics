"""Time-series helpers for cumulative and historical issue-difficulty trends."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

import pandas as pd

from hiero_analytics.data_sources.models import IssueRecord, IssueTimelineEventRecord
from hiero_analytics.domain.labels import (
    DIFFICULTY_ADVANCED,
    DIFFICULTY_BEGINNER,
    DIFFICULTY_GOOD_FIRST_ISSUE,
    DIFFICULTY_INTERMEDIATE,
)

TIMELINE_EVENT_ORDER = {
    "unlabeled": 0,
    "labeled": 1,
    "closed": 2,
    "reopened": 3,
}

# Bucket key for issues without a recognised difficulty label. Deliberately a
# local column key (like "gfi"), not the display name from domain.labels.
UNKNOWN_KEY = "unknown"

# Single source for the series' bucket keys: column orders and zeroed rows all
# derive from this table, so adding a difficulty means adding one entry here.
_DIFFICULTY_OVER_TIME_SPECS = (
    ("gfi", DIFFICULTY_GOOD_FIRST_ISSUE),
    ("beginner", DIFFICULTY_BEGINNER),
    ("intermediate", DIFFICULTY_INTERMEDIATE),
    ("advanced", DIFFICULTY_ADVANCED),
)

DIFFICULTY_OVER_TIME_COLUMN_ORDER = [key for key, _ in _DIFFICULTY_OVER_TIME_SPECS]

DIFFICULTY_OVER_TIME_ALL_COLUMN_ORDER = [
    UNKNOWN_KEY,
    *DIFFICULTY_OVER_TIME_COLUMN_ORDER,
]


def normalize_datetime(value: datetime | None) -> datetime | None:
    """Normalize a datetime to UTC, returning None if the input is None."""
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


def weekly_sample_points(start_at: datetime, end_at: datetime) -> list[datetime]:
    """Return a list of UTC datetimes spaced one week apart from start_at to end_at."""
    points: list[datetime] = []
    current = start_at

    while current <= end_at:
        points.append(current)
        current += timedelta(days=7)

    if not points or points[-1] < end_at:
        points.append(end_at)

    return points


def init_row_for_sample(sample_point: datetime) -> dict[str, int | str]:
    """Return a zeroed-out difficulty row dict for a given sample point."""
    return {
        "date": sample_point.date().isoformat(),
        **dict.fromkeys(DIFFICULTY_OVER_TIME_ALL_COLUMN_ORDER, 0),
    }


def difficulty_key_for_label(label: str | None):
    """Return the difficulty bucket key for a single label string, or None if unrecognised."""
    if not label:
        return None

    for key, spec in _DIFFICULTY_OVER_TIME_SPECS:
        if label.lower() in spec.labels:
            return key

    return None


def difficulty_key(labels: set[str]) -> str | None:
    """Return the difficulty key for an active label set, or None.

    Mirrors :func:`hiero_analytics.analysis.difficulty_analysis.assign_difficulty`:
    when several difficulty labels are active at once, the highest one wins.
    """
    normalized = {label.lower() for label in labels or []}

    for key, spec in reversed(_DIFFICULTY_OVER_TIME_SPECS):
        if spec.matches(normalized):
            return key

    return None


def timeline_events_by_issue(
    timeline_events: Iterable[object],
    *,
    event_type_order: dict[str, int] | None = None,
) -> dict[tuple[str, int], list[object]]:
    """Group timeline events by issue identity and sort them chronologically."""
    grouped: dict[tuple[str, int], list[object]] = {}

    for event in timeline_events:
        grouped.setdefault((event.repo, event.issue_number), []).append(event)

    for key in grouped:
        grouped[key].sort(
            key=lambda event: (
                normalize_datetime(event.occurred_at) or datetime.max.replace(tzinfo=UTC),
                event_type_order.get(event.event_type, 99)
                if event_type_order is not None
                else getattr(event, "event_type", ""),
            )
        )

    return grouped


def _resolve_entry_points(
    issues: list[IssueRecord],
    events_by_issue: dict[tuple[str, int], list[IssueTimelineEventRecord]],
    end_at: datetime,
    *,
    include_unknown: bool = False,
) -> dict[tuple[str, int], tuple[str, datetime]]:
    """Map each issue to the (difficulty bucket, entry timestamp) it enters the series with.

    Issues with a difficulty label enter their difficulty bucket at the most
    recent recorded label event matching it; without ``include_unknown``,
    issues with no such datable event — unlabelled, no matching event, or an
    event after the window — are excluded, so every entry point is grounded in
    a recorded event. With ``include_unknown``, those issues enter the
    ``unknown`` bucket from their creation date instead: a difficulty whose
    application date isn't recoverable can't be honestly placed on the
    timeline, but the issue is still an open, untriaged-looking one.
    """
    entry_points: dict[tuple[str, int], tuple[str, datetime]] = {}

    for issue in issues:
        current_difficulty = difficulty_key(set(issue.labels or []))

        # Find the most recent labeled event matching the current difficulty.
        label_timestamp: datetime | None = None
        if current_difficulty is not None:
            issue_events = events_by_issue.get((issue.repo, issue.number), [])
            for event in reversed(issue_events):
                if event.event_type == "labeled" and difficulty_key_for_label(event.label) == current_difficulty:
                    label_timestamp = normalize_datetime(event.occurred_at)
                    break

        if current_difficulty is not None and label_timestamp is not None and label_timestamp <= end_at:
            entry_points[(issue.repo, issue.number)] = (current_difficulty, label_timestamp)
            continue

        # Unlabelled, or labelled with no datable in-window label event: no
        # anchor for a difficulty band, so (opt-in) count the issue as unknown
        # from its creation date.
        if not include_unknown:
            continue
        entry_timestamp = normalize_datetime(issue.created_at)
        if entry_timestamp is None or entry_timestamp > end_at:
            continue
        entry_points[(issue.repo, issue.number)] = (UNKNOWN_KEY, entry_timestamp)

    return entry_points


def get_difficulty_over_time_event_based(
    issues: list[IssueRecord],
    timeline_events: list[IssueTimelineEventRecord],
    *,
    start_at: datetime,
    today: datetime | None = None,
    include_unknown: bool = False,
) -> list[dict[str, str | int]]:
    """
    Build weekly open-issue counts using only event-based forward tracking.

    Rules:
    - Only include issues created within the observation window.
    - Use the label application date (most recent labeled event) as the entry point.
    - Track forward only from the label event to the end of the window.
    - Exclude issues with no difficulty label event in the timeline, unless
      ``include_unknown`` is set — then issues without a difficulty label (or
      whose label application date isn't recoverable from events) are counted
      in an ``unknown`` bucket from their creation date onward.

    This approach avoids reconstructing historical state or mixing present-day
    snapshot data with historical events. Every difficulty data point is
    grounded in a recorded event; only the ``unknown`` bucket (opt-in) uses the
    creation date, because those issues have no label event to anchor on.
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
    issue_entry_points = _resolve_entry_points(
        filtered_issues, events_by_issue, end_at, include_unknown=include_unknown
    )

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
