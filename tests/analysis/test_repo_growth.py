"""Tests for :mod:`hiero_analytics.analysis.repo_growth`."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from hiero_analytics.analysis.repo_growth import build_repo_growth_timeline
from hiero_analytics.data_sources.models import RepositoryRecord


def _repo(name: str, created_at: datetime | None = None) -> RepositoryRecord:
    """Convenience factory for a minimal RepositoryRecord."""
    return RepositoryRecord(
        full_name=f"org/{name}",
        name=name,
        owner="org",
        created_at=created_at,
    )


class TestBuildRepoGrowthTimeline:
    """build_repo_growth_timeline produces correct monthly aggregates."""

    def test_empty_input(self) -> None:
        """Empty input list returns an empty frame with proper schema."""
        result = build_repo_growth_timeline([])
        assert list(result.columns) == ["month", "repos_created", "cumulative_repos"]
        assert result.empty

    def test_all_none_created_at(self) -> None:
        """Records with all None created_at return empty frame."""
        records = [_repo("a"), _repo("b")]
        result = build_repo_growth_timeline(records)
        assert result.empty

    def test_single_repo(self) -> None:
        """Single repo created produces 1 row with count 1."""
        records = [_repo("a", datetime(2024, 3, 15, tzinfo=UTC))]
        result = build_repo_growth_timeline(records)

        assert len(result) == 1
        assert result.iloc[0]["repos_created"] == 1
        assert result.iloc[0]["cumulative_repos"] == 1

    def test_multiple_repos_same_month(self) -> None:
        """Multiple repos in same month are aggregated."""
        records = [
            _repo("a", datetime(2024, 6, 1, tzinfo=UTC)),
            _repo("b", datetime(2024, 6, 15, tzinfo=UTC)),
            _repo("c", datetime(2024, 6, 30, tzinfo=UTC)),
        ]
        result = build_repo_growth_timeline(records)

        assert len(result) == 1
        assert result.iloc[0]["repos_created"] == 3
        assert result.iloc[0]["cumulative_repos"] == 3

    def test_multiple_months_cumulative(self) -> None:
        """Multiple months calculate running cumulative total."""
        records = [
            _repo("a", datetime(2024, 1, 10, tzinfo=UTC)),
            _repo("b", datetime(2024, 1, 20, tzinfo=UTC)),
            _repo("c", datetime(2024, 3, 5, tzinfo=UTC)),
            _repo("d", datetime(2024, 5, 1, tzinfo=UTC)),
        ]
        result = build_repo_growth_timeline(records)

        assert len(result) == 5  # Jan, Feb, Mar, Apr, May (filled zero months)
        assert list(result["repos_created"]) == [2, 0, 1, 0, 1]
        assert list(result["cumulative_repos"]) == [2, 2, 3, 3, 4]

    def test_none_created_at_excluded(self) -> None:
        """Repos with None created_at are silently dropped."""
        records = [
            _repo("has-date", datetime(2024, 2, 1, tzinfo=UTC)),
            _repo("no-date", None),
        ]
        result = build_repo_growth_timeline(records)

        assert len(result) == 1
        assert result.iloc[0]["repos_created"] == 1

    def test_sorted_chronologically(self) -> None:
        """Output is sorted by month regardless of input order."""
        records = [
            _repo("late", datetime(2024, 12, 1, tzinfo=UTC)),
            _repo("early", datetime(2024, 1, 1, tzinfo=UTC)),
            _repo("mid", datetime(2024, 6, 1, tzinfo=UTC)),
        ]
        result = build_repo_growth_timeline(records)

        months = list(result["month"])
        assert months == sorted(months)

    def test_output_dtypes(self) -> None:
        """Verify month is datetime and counts are integers."""
        records = [_repo("a", datetime(2024, 1, 1, tzinfo=UTC))]
        result = build_repo_growth_timeline(records)

        assert pd.api.types.is_datetime64_any_dtype(result["month"])
        assert pd.api.types.is_integer_dtype(result["repos_created"])
        assert pd.api.types.is_integer_dtype(result["cumulative_repos"])
