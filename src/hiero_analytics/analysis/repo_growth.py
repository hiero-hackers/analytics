"""Repo-growth timeline analytics.

Pure transformations on :class:`RepositoryRecord` lists to produce monthly
repo-creation counts and cumulative repo totals.  The data source is the
``createdAt`` timestamp that the repos GraphQL query already returns — no
extra token, no audit-log access, all-time coverage.
"""

from __future__ import annotations

import pandas as pd

from hiero_analytics.data_sources.models import RepositoryRecord


def build_repo_growth_timeline(records: list[RepositoryRecord]) -> pd.DataFrame:
    """Monthly repos-created count and cumulative total from repository metadata.

    Parameters
    ----------
    records
        Repository records with ``created_at`` timestamps (``None`` entries
        are silently dropped).

    Returns:
    -------
    pd.DataFrame
        Columns: ``month`` (period start as datetime), ``repos_created``
        (new repos that month), ``cumulative_repos`` (running total).
        Sorted chronologically.  Empty input yields an empty frame with
        the correct schema.
    """
    cols = ["month", "repos_created", "cumulative_repos"]
    rows = [{"created_at": r.created_at} for r in records if r.created_at is not None]
    if not rows:
        return pd.DataFrame(columns=cols)

    df = pd.DataFrame(rows)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    # Group by calendar month (period start).
    df["month"] = df["created_at"].dt.tz_localize(None).dt.to_period("M").dt.to_timestamp()
    monthly = df.groupby("month", as_index=False).size().rename(columns={"size": "repos_created"}).sort_values("month")
    # Fill months with zero creations so the chart and CSV have no gaps.
    full_range = pd.date_range(
        start=monthly["month"].min(),
        end=monthly["month"].max(),
        freq="MS",
    )
    monthly = monthly.set_index("month").reindex(full_range, fill_value=0).rename_axis("month").reset_index()
    monthly["cumulative_repos"] = monthly["repos_created"].cumsum()
    return monthly.reset_index(drop=True)
