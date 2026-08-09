"""Release cadence and staleness analytics.

Pure transformations on :class:`ReleaseRecord` lists — no network calls, no
file I/O (``pipelines/releases.py`` owns writing these to disk).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from hiero_analytics.analysis.dataframe_utils import records_to_dataframe, repos_to_dataframe
from hiero_analytics.data_sources.models import ReleaseRecord, RepositoryRecord

_TIMELINE_COLUMNS = ["repo", "tag_name", "published_at", "is_prerelease"]
_STALENESS_COLUMNS = [
    "repo",
    "latest_release",
    "days_since_last_release",
    "median_gap_days",
    "staleness_ratio",
]


def build_release_timeline(records: list[ReleaseRecord]) -> pd.DataFrame:
    """One row per release: repo, tag, publish date, prerelease flag.

    Full history — any window (e.g. the dashboard's ~18-month chart view) is
    applied at chart time, not baked into this table, so the CSV artifact
    stays a complete record regardless of how the chart windows it.
    """
    timeline = records_to_dataframe(
        records,
        lambda r: {
            "repo": r.repo,
            "tag_name": r.tag_name,
            "published_at": r.published_at,
            "is_prerelease": r.is_prerelease,
        },
        _TIMELINE_COLUMNS,
    )
    return timeline.sort_values(["repo", "published_at"]).reset_index(drop=True)


def build_release_staleness(
    records: list[ReleaseRecord],
    all_repos: list[RepositoryRecord],
    *,
    now: datetime | None = None,
) -> pd.DataFrame:
    """Per repo: latest release and days since, across the full repo list.

    Repos with no releases are retained with null staleness values. Published as
    a standalone artifact because release staleness is neither governance-
    dependent nor period-scoped.

    ``now`` is injectable for deterministic tests; production callers should
    leave it unset.
    """
    now = now or datetime.now(UTC)

    repo_universe = repos_to_dataframe(all_repos)[["repo"]].drop_duplicates()
    if repo_universe.empty:
        return pd.DataFrame(columns=_STALENESS_COLUMNS)

    releases = records_to_dataframe(
        records,
        lambda r: {"repo": r.repo, "published_at": r.published_at},
        ["repo", "published_at"],
    )
    if releases.empty:
        staleness = repo_universe.copy()
        staleness["latest_release"] = pd.NaT
        staleness["days_since_last_release"] = pd.array([None] * len(staleness), dtype="Int64")
        staleness["median_gap_days"] = pd.array([None] * len(staleness), dtype="Float64")
        staleness["staleness_ratio"] = pd.array([None] * len(staleness), dtype="Float64")
        return staleness[_STALENESS_COLUMNS].reset_index(drop=True)

    releases = releases.sort_values(["repo", "published_at"])
    grouped = releases.groupby("repo")["published_at"]
    latest = grouped.max().rename("latest_release")
    median_gap = grouped.apply(lambda s: s.diff().dt.days.median()).rename("median_gap_days")

    staleness = repo_universe.merge(latest, on="repo", how="left").merge(median_gap, on="repo", how="left")
    staleness["latest_release"] = pd.to_datetime(staleness["latest_release"], utc=True)
    days = (now - staleness["latest_release"]).dt.days
    staleness["days_since_last_release"] = days.astype("Int64")
    staleness["median_gap_days"] = staleness["median_gap_days"].astype("Float64")

    # A zero-day median gap (e.g. two releases tagged the same day) makes the
    # ratio undefined, not infinite — treated the same as "no cadence yet".
    safe_gap = staleness["median_gap_days"].where(staleness["median_gap_days"] > 0)
    staleness["staleness_ratio"] = (staleness["days_since_last_release"] / safe_gap).astype("Float64")

    return staleness[_STALENESS_COLUMNS].reset_index(drop=True)
