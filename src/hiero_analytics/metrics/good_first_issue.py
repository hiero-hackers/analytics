from __future__ import annotations

import pandas as pd
from typing import Dict


GFI_LABELS = {
    "good first issue",
    "good first issue candidate",
    "skill: good first issue",
}


def good_first_issue_metrics(
    df: pd.DataFrame,
) -> Dict[str, pd.DataFrame]:
    """
    Compute Good First Issue metrics from a dataframe of issues.
    """

    if df.empty:
        return {
            "yearly": pd.DataFrame(columns=["year", "count"]),
            "yearly_by_repo": pd.DataFrame(columns=["year", "repo", "count"]),
            "total_by_repo": pd.DataFrame(columns=["repo", "count"]),
        }

    # Ensure labels column exists
    if "labels" not in df.columns:
        raise ValueError("DataFrame must contain a 'labels' column")

    # Filter good first issues
    gfi_mask = df["labels"].map(
        lambda labels: bool(GFI_LABELS & set(labels or []))
    )

    gfi = df[gfi_mask]

    if gfi.empty:
        return {
            "yearly": pd.DataFrame(columns=["year", "count"]),
            "yearly_by_repo": pd.DataFrame(columns=["year", "repo", "count"]),
            "total_by_repo": pd.DataFrame(columns=["repo", "count"]),
        }

    yearly = (
        gfi.groupby("year")
        .size()
        .reset_index(name="count")
        .sort_values("year")
    )

    yearly_by_repo = (
        gfi.groupby(["year", "repo"])
        .size()
        .reset_index(name="count")
        .sort_values(["year", "repo"])
    )

    total_by_repo = (
        gfi.groupby("repo")
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )

    return {
        "yearly": yearly,
        "yearly_by_repo": yearly_by_repo,
        "total_by_repo": total_by_repo,
    }