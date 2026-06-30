"""Hiero Hackers GitHub organization analytics functions.

Pure transformations on repository and contributor activity data
to produce aggregated summaries for charting.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from hiero_analytics.analysis.dataframe_utils import repos_to_dataframe
from hiero_analytics.data_sources.models import ContributorActivityRecord

__all__ = [
    "repos_to_dataframe",
    "calculate_push_activity_summary",
    "calculate_language_distribution",
    "build_contributor_counts",
]


def calculate_push_activity_summary(
    df: pd.DataFrame,
    days: int = 30,
) -> pd.DataFrame:
    """Summarize repository push activity over a rolling window.
    
    Categorizes repositories as "Active" if pushed within the last ``days`` days,
    otherwise "Inactive". Uses UTC now as the reference point.
    
    Parameters
    ----------
    df
        Repository DataFrame with "pushed_at" column (datetime or None).
    days
        Number of days to consider "active". Defaults to 30.
    
    Returns:
    -------
    pd.DataFrame
        DataFrame with columns: "status" ("Active"/"Inactive"), "count"
    """
    if df.empty:
        return pd.DataFrame({
            "status": ["Active", "Inactive"],
            "count": [0, 0],
        })
    
    cutoff = datetime.now(UTC) - timedelta(days=days)
    
    # Categorize by push activity
    def get_status(pushed_at: datetime | None) -> str:
        if pushed_at is None:
            return "Inactive"
        return "Active" if pushed_at >= cutoff else "Inactive"
    
    df = df.copy()
    df["status"] = df["pushed_at"].apply(get_status)
    
    counts = df["status"].value_counts().to_dict()
    return pd.DataFrame([
        {"status": "Active", "count": int(counts.get("Active", 0))},
        {"status": "Inactive", "count": int(counts.get("Inactive", 0))},
    ])


def calculate_language_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """Summarize programming language distribution across repositories.
    
    Groups repositories by language, with null languages filled as "Unknown".
    
    Parameters
    ----------
    df
        Repository DataFrame with "language" column.
    
    Returns:
    -------
    pd.DataFrame
        DataFrame with columns: "language", "count", sorted by count descending.
    """
    if df.empty:
        return pd.DataFrame(columns=["language", "count"])
    
    df = df.copy()
    df["language"] = df["language"].fillna("Unknown")
    
    # Get value counts and convert to DataFrame
    counts_series = df["language"].value_counts()
    result = pd.DataFrame({
        "language": counts_series.index,
        "count": counts_series.values,
    }).reset_index(drop=True)
    
    return result


def build_contributor_counts(
    activity_records: list[ContributorActivityRecord],
) -> pd.DataFrame:
    """Count unique contributors per repository.
    
    Groups contributor activity records by repository and counts
    unique actors per repository.
    
    Parameters
    ----------
    activity_records
        List of ContributorActivityRecord objects from GitHub API.
    
    Returns:
    -------
    pd.DataFrame
        DataFrame with columns: "repo", "contributors"
    """
    if not activity_records:
        return pd.DataFrame(columns=["repo", "contributors"])
    
    df = pd.DataFrame([
        {
            "repo": record.repo,
            "actor": record.actor,
        }
        for record in activity_records
    ])
    
    counts = (
        df.groupby("repo", as_index=False)["actor"]
        .nunique()
        .rename(columns={"actor": "contributors"})
    )
    return counts
