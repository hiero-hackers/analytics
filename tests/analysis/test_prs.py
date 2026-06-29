"""Tests for pull-request onboarding analysis helpers."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from hiero_analytics.analysis.prs import (
    filter_gfi_prs,
    first_time_contributors,
    prs_to_dataframe,
)
from hiero_analytics.data_sources.models import PullRequestDifficultyRecord


def _dt(day: int) -> datetime:
    return datetime(2024, 1, day, tzinfo=timezone.utc)


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
    rec = _record(
        pr_number=7, author="alice", labels=["good first issue"], merged_day=3
    )

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
    gfi = _record(
        pr_number=1, author="a", labels=["good first issue"], merged_day=1
    )
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


# -- first_time_contributors --------------------------------------------------


def test_first_time_contributors_empty_passthrough():
    """An empty frame is returned unchanged."""
    empty = prs_to_dataframe([])
    assert first_time_contributors(empty).empty


def test_first_time_contributors_keeps_earliest_merged_per_author():
    """Each author collapses to their earliest merged PR."""
    early = _record(pr_number=1, author="alice", labels=[], merged_day=2)
    late = _record(pr_number=2, author="alice", labels=[], merged_day=9)
    other = _record(pr_number=3, author="bob", labels=[], merged_day=5)

    df = prs_to_dataframe([late, early, other])
    result = first_time_contributors(df)

    by_author = result.set_index("author")
    assert by_author.loc["alice", "pr_number"] == 1
    assert by_author.loc["bob", "pr_number"] == 3


def test_first_time_contributors_drops_null_authors():
    """Rows without an author are excluded from the result."""
    named = _record(pr_number=1, author="alice", labels=[], merged_day=1)
    anon = _record(pr_number=2, author=None, labels=[], merged_day=2)

    df = prs_to_dataframe([named, anon])
    result = first_time_contributors(df)

    assert list(result["author"]) == ["alice"]


def test_first_time_contributors_excludes_unmerged_prs():
    """A contributor whose only PR is unmerged must not appear with a NaT date.

    Regression: ``first_time_contributors`` is documented as "first merged PR
    per contributor", but without filtering on ``pr_merged_at`` an author with
    only an open PR leaked through carrying a ``NaT`` merge date.
    """
    merged = _record(pr_number=1, author="alice", labels=[], merged_day=4)
    unmerged = _record(pr_number=2, author="bob", labels=[], merged_day=4)
    # Simulate an open PR: build the frame, then null out bob's merge date.
    df = prs_to_dataframe([merged, unmerged])
    df.loc[df["author"] == "bob", "pr_merged_at"] = pd.NaT

    result = first_time_contributors(df)

    assert list(result["author"]) == ["alice"]
    assert result["pr_merged_at"].notna().all()
