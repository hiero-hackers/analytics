"""Tests for difficulty-bucket selection in the org difficulty pipeline.

These guard the regression where the Unknown bucket collapsed to zero: when
issues were filtered to *only* those labeled within the window, every surviving
issue carried a difficulty label, so the "with unknown" and "without unknown"
charts came out identical.  The Unknown bucket is therefore anchored to issue
*creation* date instead of label-application date.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hiero_analytics.data_sources.models import IssueRecord
from hiero_analytics.domain.labels import DIFFICULTY_LEVELS
from hiero_analytics.run_difficulty_org_for_repo import (
    _issues_unlabeled_created_since,
)

CUTOFF = datetime(2026, 5, 4, tzinfo=UTC)


def _issue(number: int, *, created_at: datetime, labels: list[str]) -> IssueRecord:
    return IssueRecord(
        repo="org/repo",
        number=number,
        title=f"issue {number}",
        state="OPEN",
        created_at=created_at,
        closed_at=None,
        labels=labels,
    )


def test_unknown_bucket_includes_recent_untriaged_issues():
    """An issue created in-window with no difficulty label is Unknown."""
    issues = [_issue(1, created_at=CUTOFF + timedelta(days=1), labels=["bug"])]

    unknown = _issues_unlabeled_created_since(issues, CUTOFF, DIFFICULTY_LEVELS)

    assert unknown == {("org/repo", 1)}


def test_unknown_bucket_excludes_labeled_issues():
    """A recent issue that already carries a difficulty label is not Unknown."""
    issues = [_issue(2, created_at=CUTOFF + timedelta(days=1), labels=["beginner"])]

    unknown = _issues_unlabeled_created_since(issues, CUTOFF, DIFFICULTY_LEVELS)

    assert unknown == set()


def test_unknown_bucket_excludes_issues_created_before_cutoff():
    """An older untriaged issue is anchored to creation date and excluded."""
    issues = [_issue(3, created_at=CUTOFF - timedelta(days=1), labels=[])]

    unknown = _issues_unlabeled_created_since(issues, CUTOFF, DIFFICULTY_LEVELS)

    assert unknown == set()


def test_unknown_bucket_is_disjoint_from_labeled():
    """No issue is both Unknown (untriaged) and difficulty-labeled at once."""
    issues = [
        _issue(1, created_at=CUTOFF + timedelta(days=1), labels=[]),
        _issue(2, created_at=CUTOFF + timedelta(days=2), labels=["intermediate"]),
    ]

    unknown = _issues_unlabeled_created_since(issues, CUTOFF, DIFFICULTY_LEVELS)
    labeled = {
        (i.repo, i.number)
        for i in issues
        if any(s.matches(set(i.labels)) for s in DIFFICULTY_LEVELS)
    }

    assert unknown.isdisjoint(labeled)
    assert unknown == {("org/repo", 1)}
