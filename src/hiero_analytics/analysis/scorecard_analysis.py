"""Analysis functions for converting OpenSSF Scorecard records into DataFrames."""

from __future__ import annotations

import pandas as pd

from hiero_analytics.analysis.dataframe_utils import records_to_dataframe
from hiero_analytics.data_sources.models import ScorecardRecord

CHECK_COLUMNS = [
    "Maintained",
    "Code-Review",
    "CII-Best-Practices",
    "Dangerous-Workflow",
    "Binary-Artifacts",
    "Token-Permissions",
    "Pinned-Dependencies",
    "Fuzzing",
    "License",
    "Signed-Releases",
    "Security-Policy",
    "Branch-Protection",
    "Packaging",
    "SAST",
]


def scorecard_to_dataframe(scorecards: list[ScorecardRecord]) -> pd.DataFrame:
    """Convert ScorecardRecord list into a dataframe."""
    return records_to_dataframe(
        scorecards,
        lambda s: {"repo": s.repo, "score": s.score, "date": s.date},
        ["repo", "score", "date"],
    )


def scorecard_stacked_dataframe(scorecards: list[ScorecardRecord]) -> pd.DataFrame:
    """
    Convert ScorecardRecord list into a dataframe with checks as columns.

    Missing checks are filled with 0.
    """
    if not scorecards:
        return pd.DataFrame(columns=["repo", "score", "date", *CHECK_COLUMNS])

    rows: list[dict] = []

    for s in scorecards:
        checks = s.checks or {}
        rows.append(
            {
                "repo": s.repo,
                "score": s.score,
                "date": s.date,
                **{check: checks.get(check, 0.0) for check in CHECK_COLUMNS},
            }
        )

    return pd.DataFrame(rows)
