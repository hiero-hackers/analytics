"""Tests for pull-request onboarding analysis helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from hiero_analytics.analysis.prs import (
    filter_gfi_prs,
    prs_to_dataframe,
)
from hiero_analytics.data_sources.models import PullRequestDifficultyRecord


def _dt(day: int) -> datetime:
    return datetime(2024, 1, day, tzinfo=UTC)


def _record(
    *,
    pr_number: int,
    author: str | None,
    labels: list[str],
    merged_day: int,
    repo: str = "hiero-ledger/repo",
) -> PullRequestDifficultyRecord:
    return PullRequestDifficultyRecord(
        repo=repo,
        pr_number=pr_number,
        pr_created_at=_dt(merged_day),
        pr_merged_at=_dt(merged_day),
        pr_additions=1,
        pr_deletions=0,
        pr_changed_files=1,
        issue_number=pr_number * 10,
        issue_labels=labels,
        author=author,
    )


# -- prs_to_dataframe ---------------------------------------------------------


def test_prs_to_dataframe_empty_returns_stable_schema():
    """No records still yields a DataFrame carrying the PR column schema."""
    df = prs_to_dataframe([])

    assert df.empty
    assert list(df.columns) == [
        "repo",
        "pr_number",
        "pr_created_at",
        "pr_merged_at",
        "issue_number",
        "issue_labels",
        "author",
    ]


def test_prs_to_dataframe_maps_record_fields():
    """Each record becomes a row with the mapped subset of fields."""
    rec = _record(pr_number=7, author="alice", labels=["good first issue"], merged_day=3)

    df = prs_to_dataframe([rec])

    assert len(df) == 1
    row = df.iloc[0]
    assert row["repo"] == "hiero-ledger/repo"
    assert row["pr_number"] == 7
    assert row["issue_number"] == 70
    assert row["issue_labels"] == ["good first issue"]
    assert row["author"] == "alice"


# -- filter_gfi_prs -----------------------------------------------------------


def test_filter_gfi_prs_empty_passthrough():
    """An empty frame is returned unchanged (no apply over no rows)."""
    empty = prs_to_dataframe([])
    assert filter_gfi_prs(empty).empty


def test_filter_gfi_prs_keeps_only_onboarding_labelled_rows():
    """Only PRs whose issue carries an onboarding label survive."""
    gfi = _record(pr_number=1, author="a", labels=["good first issue"], merged_day=1)
    candidate = _record(
        pr_number=2,
        author="b",
        labels=["good first issue candidate"],
        merged_day=2,
    )
    other = _record(pr_number=3, author="c", labels=["bug"], merged_day=3)
    unlabelled = _record(pr_number=4, author="d", labels=[], merged_day=4)

    df = prs_to_dataframe([gfi, candidate, other, unlabelled])
    result = filter_gfi_prs(df)

    assert set(result["pr_number"]) == {1, 2}
