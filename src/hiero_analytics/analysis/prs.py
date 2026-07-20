"""Transformations and filters for pull request difficulty records."""

from __future__ import annotations

import pandas as pd

from hiero_analytics.analysis.dataframe_utils import records_to_dataframe
from hiero_analytics.data_sources.models import PullRequestDifficultyRecord
from hiero_analytics.domain.labels import ALL_ONBOARDING

_PR_COLUMNS = [
    "repo",
    "pr_number",
    "pr_created_at",
    "pr_merged_at",
    "issue_number",
    "issue_labels",
    "author",
]


def prs_to_dataframe(
    records: list[PullRequestDifficultyRecord],
) -> pd.DataFrame:
    """Convert a list of PullRequestDifficultyRecord objects into a DataFrame.

    ``issue_number`` is a nullable integer column (``Int64``): unlinked PRs carry
    a missing value without silently promoting the linked ones to float.
    """
    df = records_to_dataframe(
        records,
        lambda r: {
            "repo": r.repo,
            "pr_number": r.pr_number,
            "pr_created_at": r.pr_created_at,
            "pr_merged_at": r.pr_merged_at,
            "issue_number": r.issue_number,
            "issue_labels": r.issue_labels,
            "author": r.author,
        },
        _PR_COLUMNS,
    )
    df["issue_number"] = df["issue_number"].astype("Int64")
    return df


def filter_gfi_prs(df: pd.DataFrame) -> pd.DataFrame:
    """Filter PR DataFrame to only rows linked to onboarding issues."""
    if df.empty:
        return df

    return df[df["issue_labels"].apply(lambda xs: ALL_ONBOARDING.matches(set(xs or [])))]


def first_time_contributors(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only the first merged PR *row* per contributor.

    Uses ``drop_duplicates`` rather than ``groupby(...).first()``: the latter
    takes the first non-null value per column independently, which can stitch
    together fields from different PRs when a column (e.g. ``issue_number``)
    is null on the first row.
    """
    if df.empty:
        return df

    return (
        df.dropna(subset=["author", "pr_merged_at"])
        .sort_values("pr_merged_at")
        .drop_duplicates(subset="author", keep="first")
        .reset_index(drop=True)
    )
