"""Tests for cumulative and historical difficulty-over-time series helpers."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from hiero_analytics.analysis.timeseries import (
    cumulative_timeseries,
    difficulty_key,
    get_difficulty_over_time_event_based,
)
from hiero_analytics.data_sources.models import IssueRecord, IssueTimelineEventRecord


def test_difficulty_key_highest_wins_on_multiple_labels():
    """Mirrors assign_difficulty: the hardest active difficulty label wins the bucket."""
    assert difficulty_key({"good first issue", "advanced"}) == "advanced"
    assert difficulty_key({"good first issue"}) == "gfi"
    assert difficulty_key({"unrelated"}) is None


def _issue(
    number: int,
    *,
    created_at: datetime,
    state: str = "OPEN",
    closed_at: datetime | None = None,
) -> IssueRecord:
    """Create an issue record for timeline tests."""
    return IssueRecord(
        repo="org/repo",
        number=number,
        title=f"Issue {number}",
        state=state,
        created_at=created_at,
        closed_at=closed_at,
        labels=[],
    )


def _event(
    issue_number: int,
    event_type: str,
    occurred_at: datetime,
    *,
    label: str | None = None,
) -> IssueTimelineEventRecord:
    """Create an issue timeline event for historical aggregation tests."""
    return IssueTimelineEventRecord(
        repo="org/repo",
        issue_number=issue_number,
        event_type=event_type,
        occurred_at=occurred_at,
        label=label,
    )


def test_cumulative_timeseries_builds_cumulative_counts() -> None:
    """The cumulative helper should still behave as a simple running total."""
    df = pd.DataFrame(
        {
            "created_at": [
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 1, 3, tzinfo=UTC),
                datetime(2024, 1, 5, tzinfo=UTC),
            ]
        }
    )

    result = cumulative_timeseries(df, "created_at")

    assert list(result["count"]) == [1, 2, 3]


def test_get_difficulty_over_time_event_based_tracks_from_label_event() -> None:
    """Event-based tracking should only count issues from their label application date forward."""
    issues = [
        IssueRecord(
            repo="org/repo",
            number=1,
            title="Issue 1",
            state="OPEN",
            created_at=datetime(2025, 1, 1, tzinfo=UTC),
            closed_at=None,
            labels=["beginner"],
        ),
        IssueRecord(
            repo="org/repo",
            number=2,
            title="Issue 2",
            state="OPEN",
            created_at=datetime(2025, 1, 5, tzinfo=UTC),
            closed_at=None,
            labels=["advanced"],
        ),
        IssueRecord(
            repo="org/repo",
            number=3,
            title="Issue 3",
            state="CLOSED",
            created_at=datetime(2025, 1, 10, tzinfo=UTC),
            closed_at=datetime(2025, 1, 20, tzinfo=UTC),
            labels=["intermediate"],
        ),
    ]
    events = [
        _event(1, "labeled", datetime(2025, 1, 3, tzinfo=UTC), label="beginner"),
        _event(2, "labeled", datetime(2025, 1, 7, tzinfo=UTC), label="advanced"),
        _event(3, "labeled", datetime(2025, 1, 12, tzinfo=UTC), label="intermediate"),
    ]

    series = get_difficulty_over_time_event_based(
        issues,
        events,
        start_at=datetime(2025, 1, 1, tzinfo=UTC),
        today=datetime(2025, 1, 22, tzinfo=UTC),
    )

    # Find rows for key dates (weekly sample points)
    row_jan_1 = next(row for row in series if row["date"] == "2025-01-01")
    row_jan_8 = next(row for row in series if row["date"] == "2025-01-08")
    row_jan_15 = next(row for row in series if row["date"] == "2025-01-15")

    # Issue 1 labeled on Jan 3 (between Jan 1 and Jan 8), so:
    # - Jan 1: not labeled yet, not counted
    # - Jan 8: labeled by then, counted
    assert row_jan_1["beginner"] == 0
    assert row_jan_8["beginner"] == 1

    # Issue 2 labeled on Jan 7 (between Jan 1 and Jan 8), so:
    # - Jan 8: labeled by then, counted
    assert row_jan_8["advanced"] == 1

    # Issue 3 labeled on Jan 12 (between Jan 8 and Jan 15) but closed on Jan 20, so:
    # - Jan 15: labeled and still open, counted
    assert row_jan_15["intermediate"] == 1


def test_get_difficulty_over_time_event_based_excludes_issues_outside_window() -> None:
    """Event-based tracking should exclude issues created outside the observation window."""
    issues = [
        IssueRecord(
            repo="org/repo",
            number=1,
            title="Issue 1",
            state="OPEN",
            created_at=datetime(2024, 12, 25, tzinfo=UTC),  # Before window
            closed_at=None,
            labels=["beginner"],
        ),
        IssueRecord(
            repo="org/repo",
            number=2,
            title="Issue 2",
            state="OPEN",
            created_at=datetime(2025, 1, 5, tzinfo=UTC),  # Within window
            closed_at=None,
            labels=["advanced"],
        ),
    ]
    events = [
        _event(1, "labeled", datetime(2024, 12, 28, tzinfo=UTC), label="beginner"),
        _event(2, "labeled", datetime(2025, 1, 7, tzinfo=UTC), label="advanced"),
    ]

    series = get_difficulty_over_time_event_based(
        issues,
        events,
        start_at=datetime(2025, 1, 1, tzinfo=UTC),
        today=datetime(2025, 1, 15, tzinfo=UTC),
    )

    # Issue 1 should not appear in counts (created before window)
    for row in series:
        assert row["beginner"] == 0

    # Issue 2 should appear from Jan 8 onward (labeled on Jan 7, sampled on Jan 8)
    row_jan_8 = next(row for row in series if row["date"] == "2025-01-08")
    assert row_jan_8["advanced"] == 1


def test_get_difficulty_over_time_event_based_excludes_issues_without_label_event() -> None:
    """Event-based tracking should exclude issues with no recorded label event."""
    issues = [
        IssueRecord(
            repo="org/repo",
            number=1,
            title="Issue 1",
            state="OPEN",
            created_at=datetime(2025, 1, 5, tzinfo=UTC),
            closed_at=None,
            labels=["beginner"],  # Has label, but no labeled event
        ),
        IssueRecord(
            repo="org/repo",
            number=2,
            title="Issue 2",
            state="OPEN",
            created_at=datetime(2025, 1, 5, tzinfo=UTC),
            closed_at=None,
            labels=["advanced"],
        ),
    ]
    events = [
        _event(2, "labeled", datetime(2025, 1, 7, tzinfo=UTC), label="advanced"),
    ]

    series = get_difficulty_over_time_event_based(
        issues,
        events,
        start_at=datetime(2025, 1, 1, tzinfo=UTC),
        today=datetime(2025, 1, 15, tzinfo=UTC),
    )

    # Issue 1 should not appear (no label event)
    for row in series:
        assert row["beginner"] == 0

    # Issue 2 should appear from Jan 8 onward (labeled on Jan 7)
    row_jan_8 = next(row for row in series if row["date"] == "2025-01-08")
    assert row_jan_8["advanced"] == 1


def test_get_difficulty_over_time_event_based_include_unknown() -> None:
    """Event-based tracking should include unknown issues only when requested."""
    issues = [
        IssueRecord(
            repo="org/repo",
            number=1,
            title="Issue 1",
            state="OPEN",
            created_at=datetime(2025, 1, 5, tzinfo=UTC),
            closed_at=None,
            labels=[],
        ),
    ]

    events = []

    series_without_unknown = get_difficulty_over_time_event_based(
        issues,
        events,
        start_at=datetime(2025, 1, 1, tzinfo=UTC),
        today=datetime(2025, 1, 15, tzinfo=UTC),
        include_unknown=False,
    )

    assert series_without_unknown == []

    series_with_unknown = get_difficulty_over_time_event_based(
        issues,
        events,
        start_at=datetime(2025, 1, 1, tzinfo=UTC),
        today=datetime(2025, 1, 15, tzinfo=UTC),
        include_unknown=True,
    )

    row_jan_8 = next(row for row in series_with_unknown if row["date"] == "2025-01-08")
    assert row_jan_8["unknown"] == 1
