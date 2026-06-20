"""Tests for the Hiero Hackers analysis module."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from hiero_analytics.analysis.hiero_hackers_analysis import (
    build_contributor_counts,
    calculate_language_distribution,
    calculate_push_activity_summary,
    repos_to_dataframe,
)
from hiero_analytics.data_sources.models import (
    ContributorActivityRecord,
    RepositoryRecord,
)


# Factory helpers for test data


def _repo(
    name: str,
    *,
    pushed_at: datetime | None = None,
    language: str | None = None,
    owner: str = "hiero-hackers",
) -> RepositoryRecord:
    """Create a test RepositoryRecord."""
    return RepositoryRecord(
        full_name=f"{owner}/{name}",
        name=name,
        owner=owner,
        pushed_at=pushed_at,
        language=language,
    )


def _activity(
    repo: str,
    actor: str,
) -> ContributorActivityRecord:
    """Create a test ContributorActivityRecord."""
    return ContributorActivityRecord(
        repo=repo,
        activity_type="OPENED",
        actor=actor,
        occurred_at=datetime.now(UTC),
        target_type="ISSUE",
        target_number=1,
    )


# ---------------------------------------------------------------------------
# repos_to_dataframe
# ---------------------------------------------------------------------------


def test_repos_to_dataframe_empty_input():
    """Empty input should return empty DataFrame with correct columns."""
    df = repos_to_dataframe([])
    assert df.empty
    assert list(df.columns) == ["repo", "pushed_at", "language"]


def test_repos_to_dataframe_with_records():
    """Should convert repository records to DataFrame."""
    now = datetime.now(UTC)
    records = [
        _repo("repo-a", pushed_at=now, language="Python"),
        _repo("repo-b", pushed_at=None, language="TypeScript"),
        _repo("repo-c", pushed_at=now - timedelta(days=10), language=None),
    ]
    df = repos_to_dataframe(records)
    
    assert len(df) == 3
    assert list(df.columns) == ["repo", "pushed_at", "language"]
    assert df["repo"].tolist() == [
        "hiero-hackers/repo-a",
        "hiero-hackers/repo-b",
        "hiero-hackers/repo-c",
    ]
    assert df["language"].tolist()[:2] == ["Python", "TypeScript"]
    assert pd.isna(df["language"].iloc[2])


# ---------------------------------------------------------------------------
# calculate_push_activity_summary
# ---------------------------------------------------------------------------


def test_calculate_push_activity_summary_empty_input():
    """Empty DataFrame should return zeros for both statuses."""
    df = pd.DataFrame(columns=["repo", "pushed_at", "language"])
    result = calculate_push_activity_summary(df, days=30)
    
    assert len(result) == 2
    assert set(result["status"]) == {"Active", "Inactive"}
    assert result[result["status"] == "Active"]["count"].values[0] == 0
    assert result[result["status"] == "Inactive"]["count"].values[0] == 0


def test_calculate_push_activity_summary_recent_pushes():
    """Repositories pushed within the window should be Active."""
    now = datetime.now(UTC)
    df = repos_to_dataframe([
        _repo("recent", pushed_at=now - timedelta(days=5)),
        _repo("old", pushed_at=now - timedelta(days=60)),
        _repo("null", pushed_at=None),
    ])
    
    result = calculate_push_activity_summary(df, days=30)
    
    assert len(result) == 2
    assert result[result["status"] == "Active"]["count"].values[0] == 1
    assert result[result["status"] == "Inactive"]["count"].values[0] == 2


# ---------------------------------------------------------------------------
# calculate_language_distribution
# ---------------------------------------------------------------------------


def test_calculate_language_distribution_empty_input():
    """Empty DataFrame should return empty result."""
    df = pd.DataFrame(columns=["repo", "pushed_at", "language"])
    result = calculate_language_distribution(df)
    
    assert result.empty
    assert list(result.columns) == ["language", "count"]


def test_calculate_language_distribution_fills_nulls():
    """Null languages should be filled as 'Unknown'."""
    df = repos_to_dataframe([
        _repo("a", language="Python"),
        _repo("b", language="Python"),
        _repo("c", language="TypeScript"),
        _repo("d", language=None),
    ])
    
    result = calculate_language_distribution(df)
    
    assert len(result) == 3
    assert "Unknown" in result["language"].values
    unknown_count = result[result["language"] == "Unknown"]["count"].values[0]
    assert unknown_count == 1


def test_calculate_language_distribution_sorted_by_count():
    """Results should be sorted by count descending."""
    df = repos_to_dataframe([
        _repo("a1", language="Rust"),
        _repo("a2", language="Rust"),
        _repo("a3", language="Rust"),
        _repo("b1", language="Go"),
        _repo("b2", language="Go"),
        _repo("c1", language="Python"),
    ])
    
    result = calculate_language_distribution(df)
    
    counts = result["count"].tolist()
    assert counts == sorted(counts, reverse=True)


# ---------------------------------------------------------------------------
# build_contributor_counts
# ---------------------------------------------------------------------------


def test_build_contributor_counts_empty_input():
    """Empty input should return empty DataFrame with correct columns."""
    df = build_contributor_counts([])
    assert df.empty
    assert list(df.columns) == ["repo", "contributors"]


def test_build_contributor_counts_groups_by_repo():
    """Should count unique actors per repository."""
    records = [
        _activity("hiero-hackers/repo-a", "alice"),
        _activity("hiero-hackers/repo-a", "bob"),
        _activity("hiero-hackers/repo-a", "alice"),  # duplicate
        _activity("hiero-hackers/repo-b", "charlie"),
        _activity("hiero-hackers/repo-b", "charlie"),  # duplicate
        _activity("hiero-hackers/repo-b", "diana"),
    ]
    
    result = build_contributor_counts(records)
    
    assert len(result) == 2
    repo_a = result[result["repo"] == "hiero-hackers/repo-a"]["contributors"].values[0]
    repo_b = result[result["repo"] == "hiero-hackers/repo-b"]["contributors"].values[0]
    assert repo_a == 2  # alice, bob
    assert repo_b == 2  # charlie, diana


def test_build_contributor_counts_with_mixed_data():
    """Should handle multiple repos with varying contributor counts."""
    records = [
        _activity("org/repo1", "u1"),
        _activity("org/repo1", "u2"),
        _activity("org/repo1", "u3"),
        _activity("org/repo2", "u4"),
    ]
    
    result = build_contributor_counts(records)
    
    assert len(result) == 2
    assert result[result["repo"] == "org/repo1"]["contributors"].values[0] == 3
    assert result[result["repo"] == "org/repo2"]["contributors"].values[0] == 1
