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
    return records_to_dataframe(
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


def filter_gfi_prs(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    return df[
        df["issue_labels"].apply(
            lambda xs: ALL_ONBOARDING.matches(set(xs or []))
        )
    ]


def first_time_contributors(df: pd.DataFrame) -> pd.DataFrame:
    """
    Keep only first merged PR per contributor.
    """
    if df.empty:
        return df

    return (
        df.dropna(subset=["author", "pr_merged_at"])
        .sort_values("pr_merged_at")
        .groupby("author", as_index=False)
        .first()
    )