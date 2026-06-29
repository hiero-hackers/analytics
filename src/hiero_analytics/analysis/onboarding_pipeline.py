from __future__ import annotations

import pandas as pd


def build_gfi_pipeline(
    gfi_yearly: pd.DataFrame,
    gfic_yearly: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build a yearly onboarding pipeline dataset.

    Combines yearly counts of Good First Issues (GFI) and Good First Issue
    Candidates (GFIC) into a single table so the two stages of the onboarding
    funnel can be compared over time.

    Parameters
    ----------
    gfi_yearly
        DataFrame with columns ["year", "count"] for GFI issues.
    gfic_yearly
        DataFrame with columns ["year", "count"] for GFIC issues.

    Returns:
    -------
    pd.DataFrame
        DataFrame with columns ["year", "gfi", "gfic"] sorted by year.
    """
    pipeline = (
        gfi_yearly.rename(columns={"count": "gfi"})
        .merge(
            gfic_yearly.rename(columns={"count": "gfic"}),
            on="year",
            how="outer",
        )
        .fillna(0)
        .astype({"gfi": int, "gfic": int})
        .sort_values("year")
    )

    return pipeline


def build_onboarding_repo_pipeline(
    gfi_total_by_repo: pd.DataFrame,
    gfic_total_by_repo: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build a repository-level onboarding pipeline dataset.

    Combines total counts of GFI and GFIC issues per repository to compare
    how different repositories contribute to the onboarding pipeline.

    Parameters
    ----------
    gfi_total_by_repo
        DataFrame with columns ["repo", "count"] for GFI issues.
    gfic_total_by_repo
        DataFrame with columns ["repo", "count"] for GFIC issues.

    Returns:
    -------
    pd.DataFrame
        DataFrame with columns ["repo", "gfi", "gfic"], sorted by GFI count.
    """
    gfi = gfi_total_by_repo.rename(columns={"count": "gfi"})
    gfic = gfic_total_by_repo.rename(columns={"count": "gfic"})

    pipeline = (
        gfi.merge(gfic, on="repo", how="outer")
        .fillna(0)
        .astype({"gfi": int, "gfic": int})
        .sort_values("gfi", ascending=False)
    )

    return pipeline