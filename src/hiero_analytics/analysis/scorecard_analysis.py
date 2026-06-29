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
        return pd.DataFrame(
            columns=["repo", "score", "date", *CHECK_COLUMNS]
        )

    rows: list[dict] = []

    for s in scorecards:
        row = {
            "repo": s.repo,
            "score": s.score,
            "date": s.date,
        }

        for check in CHECK_COLUMNS:
            row[check] = 0.0

        if s.checks:
            for name, value in s.checks.items():
                if name in CHECK_COLUMNS:
                    row[name] = value

        rows.append(row)

    df = pd.DataFrame(rows)

    return df
