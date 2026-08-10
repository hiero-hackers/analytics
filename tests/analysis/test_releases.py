"""Tests for :mod:`hiero_analytics.analysis.releases`."""

from __future__ import annotations

import math
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
        assert list(result.columns) == [
            "repo",
            "latest_release",
            "days_since_last_release",
            "median_gap_days",
            "staleness_ratio",
            "release_status",
        ]
        assert result.empty

    def test_repo_with_no_releases_still_gets_a_row(self) -> None:
        """A repo that has never released appears with null staleness, not dropped."""
        repos = [_repo("never-released")]

        result = build_release_staleness([], repos)

        assert len(result) == 1
        assert result.iloc[0]["repo"] == "org/never-released"
        assert pd.isna(result.iloc[0]["latest_release"])
        assert pd.isna(result.iloc[0]["days_since_last_release"])
        assert pd.isna(result.iloc[0]["median_gap_days"])
        assert result.iloc[0]["staleness_ratio"] == math.inf
        assert result.iloc[0]["release_status"] == "never_released"

    def test_mixed_repos_only_released_ones_get_values(self) -> None:
        """Repos with releases get real values; repos without stay null in the same frame."""
        repos = [_repo("released"), _repo("never-released")]
        records = [_release("org/released", "v1.0.0", datetime(2026, 1, 1, tzinfo=UTC))]
        now = datetime(2026, 4, 1, tzinfo=UTC)

        result = build_release_staleness(records, repos, now=now).set_index("repo")

        assert result.loc["org/released", "days_since_last_release"] == 90
        assert pd.isna(result.loc["org/never-released", "days_since_last_release"])
        assert result.loc["org/released", "release_status"] == "released"
        assert result.loc["org/never-released", "release_status"] == "never_released"

    def test_all_repositories_never_released(self) -> None:
        """All repositories are retained and marked never released when no releases exist."""
        repos = [
            _repo("a"),
            _repo("b"),
        ]

        result = build_release_staleness([], repos)

        assert list(result["repo"]) == ["org/a", "org/b"]
        assert list(result["release_status"]) == [
            "never_released",
            "never_released",
        ]
        assert (result["staleness_ratio"] == math.inf).all()

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


class TestStalenessRatio:
    """The cadence-relative signal — validated against real hiero-ledger data on #331."""

    def test_ratio_flags_a_repo_thats_gone_quiet_relative_to_its_own_pace(self) -> None:
        """A repo with a tight normal cadence that goes quiet gets a high ratio.

        Mirrors the real hiero-json-rpc-relay finding: 38 raw days looked
        unremarkable, but relative to its own 3-day cadence it was the most
        overdue repo in the org (ratio ~12.7).
        """
        repos = [_repo("relay")]
        records = [
            _release("org/relay", "v1", datetime(2026, 5, 20, tzinfo=UTC)),
            _release("org/relay", "v2", datetime(2026, 5, 23, tzinfo=UTC)),
            _release("org/relay", "v3", datetime(2026, 5, 26, tzinfo=UTC)),
            _release("org/relay", "v4", datetime(2026, 7, 2, tzinfo=UTC)),
        ]
        now = datetime(2026, 8, 9, tzinfo=UTC)

        result = build_release_staleness(records, repos, now=now)

        assert result.iloc[0]["median_gap_days"] == 3.0
        assert result.iloc[0]["days_since_last_release"] == 38
        assert round(float(result.iloc[0]["staleness_ratio"]), 2) == round(38 / 3, 2)

    def test_ratio_is_null_with_fewer_than_two_releases(self) -> None:
        """No established cadence to compare against — null, not zero or a raw-days fallback."""
        repos = [_repo("a")]
        records = [_release("org/a", "v1.0.0", datetime(2026, 1, 1, tzinfo=UTC))]

        result = build_release_staleness(records, repos)

        assert pd.isna(result.iloc[0]["median_gap_days"])
        assert pd.isna(result.iloc[0]["staleness_ratio"])

    def test_ratio_is_null_for_a_zero_day_median_gap(self) -> None:
        """Two releases tagged the same day make the ratio undefined, not infinite."""
        repos = [_repo("sameday")]
        records = [
            _release("org/sameday", "v1", datetime(2026, 1, 1, tzinfo=UTC)),
            _release("org/sameday", "v2", datetime(2026, 1, 1, tzinfo=UTC)),
        ]

        result = build_release_staleness(records, repos)

        assert result.iloc[0]["median_gap_days"] == 0.0
        assert pd.isna(result.iloc[0]["staleness_ratio"])

    def test_never_released_ranks_as_maximally_stale(self) -> None:
        """Never-released repos get an infinite ratio and remain null for cadence. Distinguishes "never released" from repos with insufficient history to establish a cadence."""
        repos = [_repo("never-released")]

        result = build_release_staleness([], repos)

        assert pd.isna(result.iloc[0]["median_gap_days"])
        assert math.isinf(result.iloc[0]["staleness_ratio"])

    def test_never_released_ranks_ahead_of_a_finite_ratio(self) -> None:
        """Sorting descending by staleness_ratio puts the never-released repo first."""
        repos = [_repo("never-released"), _repo("relay")]
        records = [
            _release("org/relay", "v1", datetime(2026, 5, 20, tzinfo=UTC)),
            _release("org/relay", "v2", datetime(2026, 5, 23, tzinfo=UTC)),
            _release("org/relay", "v3", datetime(2026, 7, 2, tzinfo=UTC)),
        ]

        result = build_release_staleness(records, repos).sort_values("staleness_ratio", ascending=False)

        assert result.iloc[0]["repo"] == "org/never-released"
        assert math.isinf(result.iloc[0]["staleness_ratio"])
        assert result.iloc[1]["repo"] == "org/relay"

    def test_low_ratio_for_a_repo_thats_right_on_its_own_schedule(self) -> None:
        """A repo currently within its own typical gap gets a ratio near or below 1."""
        repos = [_repo("steady")]
        records = [
            _release("org/steady", "v1", datetime(2026, 1, 1, tzinfo=UTC)),
            _release("org/steady", "v2", datetime(2026, 1, 15, tzinfo=UTC)),
            _release("org/steady", "v3", datetime(2026, 1, 29, tzinfo=UTC)),
        ]
        now = datetime(2026, 2, 3, tzinfo=UTC)  # 5 days since v3, 14-day cadence

        result = build_release_staleness(records, repos, now=now)

        assert result.iloc[0]["median_gap_days"] == 14.0
        assert float(result.iloc[0]["staleness_ratio"]) < 1.0
