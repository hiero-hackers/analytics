from __future__ import annotations

import pandas as pd


def build_gfi_pipeline(
    gfi_yearly: pd.DataFrame,
    gfic_yearly: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build GFIC → GFI pipeline dataset.
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
    Build stacked dataset showing onboarding pipeline per repository.
    """

    gfi = gfi_total_by_repo.rename(columns={"count": "gfi"})
    gfic = gfic_total_by_repo.rename(columns={"count": "gfic"})

    pipeline = (
        gfi.merge(gfic, on="repo", how="outer")
        .fillna(0)
        .sort_values("gfi", ascending=False)
    )

    return pipeline