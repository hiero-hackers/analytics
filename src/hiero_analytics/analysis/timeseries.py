"""Time-series helpers for cumulative and historical issue-difficulty trends."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from hiero_analytics.data_sources.models import IssueRecord, IssueTimelineEventRecord
from hiero_analytics.domain.labels import (
    DIFFICULTY_ADVANCED,
    DIFFICULTY_BEGINNER,
    DIFFICULTY_GOOD_FIRST_ISSUE,
    DIFFICULTY_INTERMEDIATE,
)

DIFFICULTY_OVER_TIME_COLUMN_ORDER = [
    "gfi",
    "beginner",
    "intermediate",
    "advanced",
]

_DIFFICULTY_OVER_TIME_SPECS = (
    ("gfi", DIFFICULTY_GOOD_FIRST_ISSUE),
    ("beginner", DIFFICULTY_BEGINNER),
    ("intermediate", DIFFICULTY_INTERMEDIATE),
    ("advanced", DIFFICULTY_ADVANCED),
)
TIMELINE_EVENT_ORDER = {
    "unlabeled": 0,
    "labeled": 1,
    "closed": 2,
    "reopened": 3,
}


def normalize_datetime(value: datetime | None) -> datetime | None:
    """Return a timezone-aware UTC datetime for stable comparisons."""
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


def _difficulty_key(labels: set[str]) -> str | None:
    """Return the first configured difficulty key that matches an active label set."""
    normalized = set(labels or [])

    for key, spec in _DIFFICULTY_OVER_TIME_SPECS:
        if spec.matches(normalized):
            return key

    return None


def _weekly_sample_points(start_at: datetime, end_at: datetime) -> list[datetime]:
    """Build inclusive weekly sample points from the first issue to now."""
    points: list[datetime] = []
    current = start_at

    while current <= end_at:
        points.append(current)
        current += timedelta(days=7)

    if not points or points[-1] < end_at:
        points.append(end_at)

    return points


def _difficulty_key_for_label(label: str | None) -> str | None:
    """Map a single label name to its logical difficulty bucket key."""
    if not label:
        return None

    for key, spec in _DIFFICULTY_OVER_TIME_SPECS:
        if label.lower() in spec.labels:
            return key

    return None


def _bucket_from_active_labels(active_labels: set[str], is_open: bool) -> str | None:
    """Resolve the visible difficulty bucket for an issue at a point in time."""
    if not is_open:
        return None

    return _difficulty_key(active_labels)


def _timeline_events_by_issue(
    timeline_events: list[IssueTimelineEventRecord],
) -> dict[tuple[str, int], list[IssueTimelineEventRecord]]:
    """Group relevant timeline events by issue identity."""
    grouped: dict[tuple[str, int], list[IssueTimelineEventRecord]] = {}

    for event in timeline_events:
        grouped.setdefault((event.repo, event.issue_number), []).append(event)

    for key in grouped:
        grouped[key].sort(
            key=lambda event: (
                normalize_datetime(event.occurred_at),
                TIMELINE_EVENT_ORDER.get(event.event_type, 99),
            )
        )

    return grouped


def _difficulty_intervals_for_issue(
    issue: IssueRecord,
    issue_events: list[IssueTimelineEventRecord],
    *,
    end_at: datetime,
) -> list[tuple[str, datetime, datetime]]:
    """Build historical difficulty-state intervals for one issue."""
    created_at = normalize_datetime(issue.created_at)
    closed_at = normalize_datetime(issue.closed_at)

    if created_at is None:
        return []

    active_difficulty_labels: set[str] = set()
    is_open = True
    current_bucket = _bucket_from_active_labels(active_difficulty_labels, is_open)
    current_start = created_at
    intervals: list[tuple[str, datetime, datetime]] = []

    for event in issue_events:
        occurred_at = normalize_datetime(event.occurred_at)
        if occurred_at is None or occurred_at < created_at:
            continue

        difficulty_key = _difficulty_key_for_label(event.label)
        if event.event_type == "labeled" and difficulty_key is not None and event.label is not None:
            active_difficulty_labels.add(event.label)
        elif event.event_type == "unlabeled" and difficulty_key is not None and event.label is not None:
            active_difficulty_labels.discard(event.label)
        elif event.event_type == "closed":
            is_open = False
        elif event.event_type == "reopened":
            is_open = True

        next_bucket = _bucket_from_active_labels(active_difficulty_labels, is_open)
        if next_bucket == current_bucket:
            continue

        if current_bucket is not None and current_start < occurred_at:
            intervals.append((current_bucket, current_start, occurred_at))

        current_bucket = next_bucket
        current_start = occurred_at

    if current_bucket is None:
        return intervals

    terminal_end = end_at
    if issue.state.lower() == "closed" and closed_at is not None:
        terminal_end = min(terminal_end, closed_at)
    else:
        terminal_end = end_at + timedelta(microseconds=1)

    if current_start < terminal_end:
        intervals.append((current_bucket, current_start, terminal_end))

    return intervals


def _current_difficulty_labels(issue: IssueRecord) -> set[str]:
    """Return the currently active difficulty labels on an issue."""
    return {
        label.lower()
        for label in issue.labels
        if _difficulty_key_for_label(label) is not None
    }


def issue_overlaps_window(issue: IssueRecord, start_at: datetime, end_at: datetime) -> bool:
    """Return whether an issue is open at any point inside a window."""
    created_at = normalize_datetime(issue.created_at)
    closed_at = normalize_datetime(issue.closed_at)

    if created_at is None or created_at > end_at:
        return False

    return closed_at is None or closed_at > start_at


def _windowed_difficulty_intervals_for_issue(
    issue: IssueRecord,
    issue_events: list[IssueTimelineEventRecord],
    *,
    start_at: datetime,
    end_at: datetime,
) -> list[tuple[str, datetime, datetime]]:
    """Build difficulty-state intervals within a bounded time window."""
    created_at = normalize_datetime(issue.created_at)
    if created_at is None or created_at > end_at:
        return []

    effective_start = max(start_at, created_at)
    current_start = effective_start
    intervals: list[tuple[str, datetime, datetime]] = []

    if created_at > start_at:
        active_difficulty_labels: set[str] = set()
        is_open = True
    else:
        active_difficulty_labels = _current_difficulty_labels(issue)
        is_open = issue.state.lower() == "open"

        relevant_events = [
            event
            for event in issue_events
            if effective_start <= normalize_datetime(event.occurred_at) <= end_at
        ]

        for event in reversed(relevant_events):
            difficulty_key = _difficulty_key_for_label(event.label)

            if event.event_type == "labeled" and difficulty_key is not None and event.label is not None:
                active_difficulty_labels.discard(event.label.lower())
            elif event.event_type == "unlabeled" and difficulty_key is not None and event.label is not None:
                active_difficulty_labels.add(event.label.lower())
            elif event.event_type == "closed":
                is_open = True
            elif event.event_type == "reopened":
                is_open = False

    current_bucket = _bucket_from_active_labels(active_difficulty_labels, is_open)

    for event in issue_events:
        occurred_at = normalize_datetime(event.occurred_at)
        if occurred_at is None or occurred_at < effective_start or occurred_at > end_at:
            continue

        difficulty_key = _difficulty_key_for_label(event.label)
        if event.event_type == "labeled" and difficulty_key is not None and event.label is not None:
            active_difficulty_labels.add(event.label.lower())
        elif event.event_type == "unlabeled" and difficulty_key is not None and event.label is not None:
            active_difficulty_labels.discard(event.label.lower())
        elif event.event_type == "closed":
            is_open = False
        elif event.event_type == "reopened":
            is_open = True

        next_bucket = _bucket_from_active_labels(active_difficulty_labels, is_open)
        if next_bucket == current_bucket:
            continue

        if current_bucket is not None and current_start < occurred_at:
            intervals.append((current_bucket, current_start, occurred_at))

        current_bucket = next_bucket
        current_start = occurred_at

    if current_bucket is not None and current_start <= end_at:
        intervals.append((current_bucket, current_start, end_at + timedelta(microseconds=1)))

    return intervals


def get_difficulty_over_time(
    issues: list[IssueRecord],
    timeline_events: list[IssueTimelineEventRecord],
    *,
    today: datetime | None = None,
) -> list[dict[str, str | int]]:
    """
    Build weekly open-issue counts per historical difficulty state over time.

    Difficulty state is reconstructed from issue timeline events:
    - ``labeled`` / ``unlabeled`` control difficulty labels over time
    - ``closed`` / ``reopened`` control whether the issue is open

    Open issues without an active difficulty label are excluded.
    """
    if not issues:
        return []

    end_at = normalize_datetime(today) or datetime.now(UTC)
    start_at = min(
        created_at
        for issue in issues
        if (created_at := normalize_datetime(issue.created_at)) is not None
    )

    if end_at < start_at:
        end_at = start_at

    events_by_issue = _timeline_events_by_issue(timeline_events)
    intervals_by_issue = [
        _difficulty_intervals_for_issue(
            issue,
            events_by_issue.get((issue.repo, issue.number), []),
            end_at=end_at,
        )
        for issue in issues
    ]

    series: list[dict[str, str | int]] = []

    for sample_point in _weekly_sample_points(start_at, end_at):
        row: dict[str, str | int] = {
            "date": sample_point.date().isoformat(),
            "gfi": 0,
            "beginner": 0,
            "intermediate": 0,
            "advanced": 0,
        }

        for intervals in intervals_by_issue:
            for bucket, interval_start, interval_end in intervals:
                if interval_start <= sample_point < interval_end:
                    row[bucket] += 1
                    break

        series.append(row)

    return series


def get_difficulty_over_time_windowed(
    issues: list[IssueRecord],
    timeline_events: list[IssueTimelineEventRecord],
    *,
    start_at: datetime,
    today: datetime | None = None,
) -> list[dict[str, str | int]]:
    """Build weekly historical open-issue counts within a bounded window."""
    if not issues:
        return []

    end_at = normalize_datetime(today) or datetime.now(UTC)
    start_at = normalize_datetime(start_at) or end_at

    if end_at < start_at:
        end_at = start_at

    filtered_issues = [issue for issue in issues if issue_overlaps_window(issue, start_at, end_at)]
    if not filtered_issues:
        return []

    events_by_issue = _timeline_events_by_issue(timeline_events)
    intervals_by_issue = [
        _windowed_difficulty_intervals_for_issue(
            issue,
            events_by_issue.get((issue.repo, issue.number), []),
            start_at=start_at,
            end_at=end_at,
        )
        for issue in filtered_issues
    ]

    series: list[dict[str, str | int]] = []
    for sample_point in _weekly_sample_points(start_at, end_at):
        row: dict[str, str | int] = {
            "date": sample_point.date().isoformat(),
            "gfi": 0,
            "beginner": 0,
            "intermediate": 0,
            "advanced": 0,
        }

        for intervals in intervals_by_issue:
            for bucket, interval_start, interval_end in intervals:
                if interval_start <= sample_point < interval_end:
                    row[bucket] += 1
                    break

        series.append(row)

    return series


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
        if (created := normalize_datetime(issue.created_at)) is not None
        and start_at <= created <= end_at
    ]

    if not filtered_issues:
        return []

    # Group events by issue.
    events_by_issue = _timeline_events_by_issue(timeline_events)

    # For each issue, find the most recent labeled event for its current difficulty.
    issue_entry_points: dict[tuple[str, int], tuple[str, datetime]] = {}

    for issue in filtered_issues:
        current_difficulty = _difficulty_key(set(issue.labels or []))
        if current_difficulty is None:
            # Skip issues with no current difficulty label.
            continue

        issue_events = events_by_issue.get((issue.repo, issue.number), [])

        # Find the most recent labeled event for this difficulty.
        most_recent_label_event: IssueTimelineEventRecord | None = None
        for event in reversed(issue_events):
            if event.event_type == "labeled" and _difficulty_key_for_label(event.label) == current_difficulty:
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
    sample_points = _weekly_sample_points(start_at, end_at)

    # Generate weekly rows.
    series: list[dict[str, str | int]] = []

    for sample_point in sample_points:
        row: dict[str, str | int] = {
            "date": sample_point.date().isoformat(),
            "gfi": 0,
            "beginner": 0,
            "intermediate": 0,
            "advanced": 0,
        }

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


def getDifficultyOverTime(
    issues: list[IssueRecord],
    timeline_events: list[IssueTimelineEventRecord],
    *,
    today: datetime | None = None,
) -> list[dict[str, str | int]]:
    """Compatibility wrapper for callers expecting camelCase naming."""
    return get_difficulty_over_time(issues, timeline_events, today=today)


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

    out = (
        df[[date_col]]
        .dropna()
        .sort_values(date_col)
        .assign(count=1)
    )

    out["count"] = out["count"].cumsum()

    return out.reset_index(drop=True)
