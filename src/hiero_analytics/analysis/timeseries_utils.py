"""Shared helpers for timeseries analysis."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

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
        "gfi": 0,
        "beginner": 0,
        "intermediate": 0,
        "advanced": 0,
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


def aggregate_intervals_to_series(
    intervals_by_issue: Iterable[Iterable[tuple[str, datetime, datetime]]],
    sample_points: Iterable[datetime],
) -> list[dict[str, int | str]]:
    """Aggregate open-interval data into a weekly series of difficulty bucket counts."""
    series: list[dict[str, int | str]] = []

    for sample_point in sample_points:
        row = init_row_for_sample(sample_point)

        for intervals in intervals_by_issue:
            for bucket, interval_start, interval_end in intervals:
                if interval_start <= sample_point < interval_end:
                    row[bucket] += 1
                    break

        series.append(row)

    return series
