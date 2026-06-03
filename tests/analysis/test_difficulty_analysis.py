"""Tests for the consolidated difficulty classification and selection helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from hiero_analytics.analysis.difficulty_analysis import (
    assign_difficulty,
    build_difficulty_dataframe,
    issues_labeled_since,
    issues_unlabeled_created_since,
)
from hiero_analytics.data_sources.models import IssueRecord, IssueTimelineEventRecord
from hiero_analytics.domain.labels import (
    DIFFICULTY_BEGINNER,
    DIFFICULTY_LEVELS,
    UNKNOWN_DIFFICULTY,
)

CUTOFF = datetime(2026, 5, 4, tzinfo=UTC)


def _issue(
    number: int,
    *,
    created_at: datetime,
    labels: list[str],
    repo: str = "org/repo",
) -> IssueRecord:
    return IssueRecord(
        repo=repo,
        number=number,
        title=f"issue {number}",
        state="OPEN",
        created_at=created_at,
        closed_at=None,
        labels=labels,
    )


def _event(
    number: int,
    event_type: str,
    *,
    occurred_at: datetime,
    label: str | None = None,
    repo: str = "org/repo",
) -> IssueTimelineEventRecord:
    return IssueTimelineEventRecord(
        repo=repo,
        issue_number=number,
        event_type=event_type,
        occurred_at=occurred_at,
        label=label,
    )


# ---------------------------------------------------------------------------
# assign_difficulty
# ---------------------------------------------------------------------------


def test_assign_difficulty_defaults_to_difficulty_levels():
    """Calling without explicit specs classifies against DIFFICULTY_LEVELS."""
    assert assign_difficulty(["beginner"]) == "Beginner"
    assert assign_difficulty(["Skill: Advanced"]) == "Advanced"


def test_assign_difficulty_unmatched_is_unknown():
    """A label set with no difficulty label falls into Unknown."""
    assert assign_difficulty(["bug"]) == UNKNOWN_DIFFICULTY


def test_assign_difficulty_handles_none():
    """A missing label list is treated as empty, not an error."""
    assert assign_difficulty(None) == UNKNOWN_DIFFICULTY


def test_assign_difficulty_respects_explicit_specs():
    """Only the provided specs are considered when classifying."""
    assert assign_difficulty(["beginner"], (DIFFICULTY_BEGINNER,)) == "Beginner"
    assert assign_difficulty(["advanced"], (DIFFICULTY_BEGINNER,)) == UNKNOWN_DIFFICULTY


# ---------------------------------------------------------------------------
# build_difficulty_dataframe
# ---------------------------------------------------------------------------


def test_build_difficulty_dataframe_orders_specs_then_unknown():
    """Rows follow spec order and always end with an Unknown bucket."""
    df = pd.DataFrame(
        {
            "labels": [["beginner"], ["advanced"], ["bug"], []],
            "state": ["open", "open", "open", "open"],
        }
    )

    result = build_difficulty_dataframe(df)

    assert list(result["difficulty"]) == [spec.name for spec in DIFFICULTY_LEVELS] + [
        UNKNOWN_DIFFICULTY
    ]
    counts = dict(zip(result["difficulty"], result["count"], strict=True))
    assert counts["Beginner"] == 1
    assert counts["Advanced"] == 1
    assert counts["Good First Issue"] == 0
    assert counts[UNKNOWN_DIFFICULTY] == 2


def test_build_difficulty_dataframe_counts_sum_to_total():
    """Single-assignment means bucket counts sum to the issue total."""
    df = pd.DataFrame({"labels": [["beginner"], ["advanced"], ["bug"]]})

    result = build_difficulty_dataframe(df)

    assert int(result["count"].sum()) == len(df)


def test_build_difficulty_dataframe_filters_by_state():
    """The optional state filter restricts the aggregation."""
    df = pd.DataFrame(
        {
            "labels": [["beginner"], ["advanced"]],
            "state": ["open", "closed"],
        }
    )

    result = build_difficulty_dataframe(df, state="open")
    counts = dict(zip(result["difficulty"], result["count"], strict=True))

    assert counts["Beginner"] == 1
    assert counts["Advanced"] == 0


def test_build_difficulty_dataframe_empty_is_all_zero():
    """An empty frame yields every bucket at zero, not an error."""
    df = pd.DataFrame({"labels": []})

    result = build_difficulty_dataframe(df)

    assert int(result["count"].sum()) == 0
    assert list(result["difficulty"]) == [spec.name for spec in DIFFICULTY_LEVELS] + [
        UNKNOWN_DIFFICULTY
    ]


# ---------------------------------------------------------------------------
# issues_labeled_since (timeline reconstruction)
# ---------------------------------------------------------------------------


def test_labeled_within_window_qualifies():
    """A difficulty label applied inside the window marks the issue as labeled."""
    issues = [_issue(1, created_at=CUTOFF - timedelta(days=10), labels=["beginner"])]
    events = [_event(1, "labeled", occurred_at=CUTOFF + timedelta(days=2), label="beginner")]

    result = issues_labeled_since(issues, events, CUTOFF, DIFFICULTY_LEVELS)

    assert result == {("org/repo", 1)}


def test_label_applied_before_window_does_not_qualify():
    """A still-active label applied *before* the cutoff must be excluded.

    Regression: with full-history timeline events, an old open issue that still
    carries a difficulty label would otherwise be counted as "labeled in the
    last 30 days" even though the label was applied long ago.
    """
    issues = [_issue(1, created_at=CUTOFF - timedelta(days=200), labels=["good first issue"])]
    events = [
        _event(1, "labeled", occurred_at=CUTOFF - timedelta(days=150), label="good first issue"),
    ]

    result = issues_labeled_since(issues, events, CUTOFF, DIFFICULTY_LEVELS)

    assert result == set()


def test_label_applied_exactly_at_cutoff_qualifies():
    """The cutoff boundary is inclusive (applied_at == cutoff qualifies)."""
    issues = [_issue(1, created_at=CUTOFF - timedelta(days=10), labels=["beginner"])]
    events = [_event(1, "labeled", occurred_at=CUTOFF, label="beginner")]

    result = issues_labeled_since(issues, events, CUTOFF, DIFFICULTY_LEVELS)

    assert result == {("org/repo", 1)}


def test_label_applied_one_microsecond_before_cutoff_excluded():
    """Just outside the window (a microsecond early) must not qualify."""
    issues = [_issue(1, created_at=CUTOFF - timedelta(days=10), labels=["beginner"])]
    events = [_event(1, "labeled", occurred_at=CUTOFF - timedelta(microseconds=1), label="beginner")]

    result = issues_labeled_since(issues, events, CUTOFF, DIFFICULTY_LEVELS)

    assert result == set()


def test_relabel_within_window_after_earlier_removal_qualifies():
    """A label removed then re-added in-window qualifies via the newer event, not the original."""
    issues = [_issue(1, created_at=CUTOFF - timedelta(days=300), labels=["beginner"])]
    events = [
        _event(1, "labeled", occurred_at=CUTOFF - timedelta(days=200), label="beginner"),
        _event(1, "unlabeled", occurred_at=CUTOFF - timedelta(days=180), label="beginner"),
        _event(1, "labeled", occurred_at=CUTOFF + timedelta(days=3), label="beginner"),
    ]

    result = issues_labeled_since(issues, events, CUTOFF, DIFFICULTY_LEVELS)

    assert result == {("org/repo", 1)}


def test_naive_cutoff_is_normalized():
    """A timezone-naive cutoff is normalized to UTC rather than raising."""
    naive_cutoff = datetime(2026, 5, 4)  # noqa: DTZ001 - deliberately naive for the test
    issues = [_issue(1, created_at=datetime(2026, 4, 24, tzinfo=UTC), labels=["beginner"])]
    events = [_event(1, "labeled", occurred_at=datetime(2026, 5, 6, tzinfo=UTC), label="beginner")]

    result = issues_labeled_since(issues, events, naive_cutoff, DIFFICULTY_LEVELS)

    assert result == {("org/repo", 1)}


def test_event_label_matching_is_case_insensitive():
    """A mixed-case event label still matches the lower-cased difficulty specs."""
    issues = [_issue(1, created_at=CUTOFF - timedelta(days=10), labels=["Good First Issue"])]
    events = [_event(1, "labeled", occurred_at=CUTOFF + timedelta(days=2), label="Good First Issue")]

    result = issues_labeled_since(issues, events, CUTOFF, DIFFICULTY_LEVELS)

    assert result == {("org/repo", 1)}


def test_label_then_unlabeled_does_not_qualify():
    """A label added then removed leaves no active difficulty label."""
    issues = [_issue(1, created_at=CUTOFF - timedelta(days=10), labels=[])]
    events = [
        _event(1, "labeled", occurred_at=CUTOFF + timedelta(days=1), label="beginner"),
        _event(1, "unlabeled", occurred_at=CUTOFF + timedelta(days=3), label="beginner"),
    ]

    result = issues_labeled_since(issues, events, CUTOFF, DIFFICULTY_LEVELS)

    assert result == set()


def test_unordered_events_are_sorted_before_replay():
    """Out-of-order events (unlabel before relabel) still resolve to active."""
    issues = [_issue(1, created_at=CUTOFF - timedelta(days=10), labels=["advanced"])]
    # Provided newest-first; the helper must sort chronologically before replay.
    events = [
        _event(1, "labeled", occurred_at=CUTOFF + timedelta(days=5), label="advanced"),
        _event(1, "unlabeled", occurred_at=CUTOFF + timedelta(days=2), label="advanced"),
    ]

    result = issues_labeled_since(issues, events, CUTOFF, DIFFICULTY_LEVELS)

    assert result == {("org/repo", 1)}


def test_events_for_unknown_issues_are_ignored():
    """Repository-wide events for issues outside the fetched set are skipped."""
    issues = [_issue(1, created_at=CUTOFF - timedelta(days=10), labels=[])]
    events = [_event(999, "labeled", occurred_at=CUTOFF + timedelta(days=1), label="beginner")]

    result = issues_labeled_since(issues, events, CUTOFF, DIFFICULTY_LEVELS)

    assert result == set()


def test_non_difficulty_label_events_are_ignored():
    """Only difficulty labels count; a 'bug' label does not qualify the issue."""
    issues = [_issue(1, created_at=CUTOFF - timedelta(days=10), labels=["bug"])]
    events = [
        _event(1, "labeled", occurred_at=CUTOFF + timedelta(days=1), label="bug"),
        _event(1, "closed", occurred_at=CUTOFF + timedelta(days=2), label=None),
    ]

    result = issues_labeled_since(issues, events, CUTOFF, DIFFICULTY_LEVELS)

    assert result == set()


def test_created_after_cutoff_with_label_qualifies_via_fallback():
    """A recent issue carrying a difficulty label but no event is still captured."""
    issues = [_issue(1, created_at=CUTOFF + timedelta(days=1), labels=["intermediate"])]

    result = issues_labeled_since(issues, [], CUTOFF, DIFFICULTY_LEVELS)

    assert result == {("org/repo", 1)}


def test_created_after_cutoff_without_label_is_not_captured():
    """The fallback only applies to recent issues that actually carry a label."""
    issues = [_issue(1, created_at=CUTOFF + timedelta(days=1), labels=["bug"])]

    result = issues_labeled_since(issues, [], CUTOFF, DIFFICULTY_LEVELS)

    assert result == set()


# ---------------------------------------------------------------------------
# issues_unlabeled_created_since (the Unknown bucket)
# ---------------------------------------------------------------------------


def test_unknown_bucket_includes_recent_untriaged_issues():
    """An issue created in-window with no difficulty label is Unknown."""
    issues = [_issue(1, created_at=CUTOFF + timedelta(days=1), labels=["bug"])]

    unknown = issues_unlabeled_created_since(issues, CUTOFF, DIFFICULTY_LEVELS)

    assert unknown == {("org/repo", 1)}


def test_unknown_bucket_excludes_labeled_issues():
    """A recent issue that already carries a difficulty label is not Unknown."""
    issues = [_issue(2, created_at=CUTOFF + timedelta(days=1), labels=["beginner"])]

    unknown = issues_unlabeled_created_since(issues, CUTOFF, DIFFICULTY_LEVELS)

    assert unknown == set()


def test_unknown_bucket_excludes_issues_created_before_cutoff():
    """An older untriaged issue is anchored to creation date and excluded."""
    issues = [_issue(3, created_at=CUTOFF - timedelta(days=1), labels=[])]

    unknown = issues_unlabeled_created_since(issues, CUTOFF, DIFFICULTY_LEVELS)

    assert unknown == set()


def test_unknown_bucket_is_disjoint_from_labeled():
    """No issue is both Unknown (untriaged) and difficulty-labeled at once."""
    issues = [
        _issue(1, created_at=CUTOFF + timedelta(days=1), labels=[]),
        _issue(2, created_at=CUTOFF + timedelta(days=2), labels=["intermediate"]),
    ]

    unknown = issues_unlabeled_created_since(issues, CUTOFF, DIFFICULTY_LEVELS)
    labeled = {
        (i.repo, i.number)
        for i in issues
        if any(s.matches(set(i.labels)) for s in DIFFICULTY_LEVELS)
    }

    assert unknown.isdisjoint(labeled)
    assert unknown == {("org/repo", 1)}
