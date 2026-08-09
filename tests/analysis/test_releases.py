"""Tests for :mod:`hiero_analytics.analysis.releases`."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from hiero_analytics.analysis.releases import build_release_staleness, build_release_timeline
from hiero_analytics.data_sources.models import ReleaseRecord, RepositoryRecord


def _repo(name: str) -> RepositoryRecord:
    """Convenience factory for a minimal RepositoryRecord."""
    return RepositoryRecord(full_name=f"org/{name}", name=name, owner="org")


def _release(
    repo: str,
    tag_name: str,
    published_at: datetime,
    *,
    is_prerelease: bool = False,
    name: str | None = None,
) -> ReleaseRecord:
    """Convenience factory for a minimal ReleaseRecord."""
    return ReleaseRecord(
        repo=repo,
        tag_name=tag_name,
        name=name or tag_name,
        published_at=published_at,
        is_prerelease=is_prerelease,
    )


class TestBuildReleaseTimeline:
    """build_release_timeline produces one row per release, sorted chronologically per repo."""

    def test_empty_input(self) -> None:
        """Empty input list returns an empty frame with the correct schema."""
        result = build_release_timeline([])
        assert list(result.columns) == ["repo", "tag_name", "published_at", "is_prerelease"]
        assert result.empty

    def test_sorts_by_repo_then_published_at(self) -> None:
        """Rows are sorted repo-major, chronologically within a repo."""
        records = [
            _release("org/b", "v2.0.0", datetime(2026, 2, 1, tzinfo=UTC)),
            _release("org/a", "v1.1.0", datetime(2026, 3, 1, tzinfo=UTC)),
            _release("org/a", "v1.0.0", datetime(2026, 1, 1, tzinfo=UTC)),
        ]

        result = build_release_timeline(records)

        assert list(result["repo"]) == ["org/a", "org/a", "org/b"]
        assert list(result["tag_name"]) == ["v1.0.0", "v1.1.0", "v2.0.0"]

    def test_prerelease_flag_is_preserved(self) -> None:
        """is_prerelease passes through unchanged."""
        records = [_release("org/a", "v1.0.0-rc1", datetime(2026, 1, 1, tzinfo=UTC), is_prerelease=True)]

        result = build_release_timeline(records)

        assert bool(result.iloc[0]["is_prerelease"]) is True


class TestBuildReleaseStaleness:
    """build_release_staleness is honest-denominator: every repo gets a row."""

    def test_empty_repo_list(self) -> None:
        """No repos at all returns an empty frame with the correct schema."""
        result = build_release_staleness([], [])
        assert list(result.columns) == ["repo", "latest_release", "days_since_last_release"]
        assert result.empty

    def test_repo_with_no_releases_still_gets_a_row(self) -> None:
        """A repo that has never released appears with null staleness, not dropped."""
        repos = [_repo("never-released")]

        result = build_release_staleness([], repos)

        assert len(result) == 1
        assert result.iloc[0]["repo"] == "org/never-released"
        assert pd.isna(result.iloc[0]["latest_release"])
        assert pd.isna(result.iloc[0]["days_since_last_release"])

    def test_mixed_repos_only_released_ones_get_values(self) -> None:
        """Repos with releases get real values; repos without stay null in the same frame."""
        repos = [_repo("released"), _repo("never-released")]
        records = [_release("org/released", "v1.0.0", datetime(2026, 1, 1, tzinfo=UTC))]
        now = datetime(2026, 4, 1, tzinfo=UTC)

        result = build_release_staleness(records, repos, now=now).set_index("repo")

        assert result.loc["org/released", "days_since_last_release"] == 90
        assert pd.isna(result.loc["org/never-released", "days_since_last_release"])

    def test_latest_release_picks_the_most_recent_tag(self) -> None:
        """days_since_last_release is computed from the newest release, not the oldest."""
        repos = [_repo("a")]
        records = [
            _release("org/a", "v1.0.0", datetime(2026, 1, 1, tzinfo=UTC)),
            _release("org/a", "v1.1.0", datetime(2026, 3, 1, tzinfo=UTC)),
        ]
        now = datetime(2026, 3, 11, tzinfo=UTC)

        result = build_release_staleness(records, repos, now=now)

        assert result.iloc[0]["latest_release"] == pd.Timestamp("2026-03-01", tz="UTC")
        assert result.iloc[0]["days_since_last_release"] == 10

    def test_releases_for_a_repo_not_in_the_universe_are_ignored(self) -> None:
        """A release for a repo outside all_repos doesn't fabricate an extra row.

        (e.g. a repo that's since been archived/removed from the org listing.)
        """
        repos = [_repo("a")]
        records = [_release("org/some-other-repo", "v1.0.0", datetime(2026, 1, 1, tzinfo=UTC))]

        result = build_release_staleness(records, repos)

        assert list(result["repo"]) == ["org/a"]
        assert pd.isna(result.iloc[0]["days_since_last_release"])
