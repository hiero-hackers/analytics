from __future__ import annotations

import pandas as pd

from hiero_analytics.domain.labels import (
    DIFFICULTY_BEGINNER,
    DIFFICULTY_GOOD_FIRST_ISSUE,
    DIFFICULTY_INTERMEDIATE,
    DIFFICULTY_ADVANCED,
)


def difficulty_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute difficulty distribution for issues.
    """

    if df.empty:
        return pd.DataFrame(columns=["difficulty", "count"])

    groups = {
        DIFFICULTY_GOOD_FIRST_ISSUE.name: DIFFICULTY_GOOD_FIRST_ISSUE.labels,
        DIFFICULTY_BEGINNER.name: DIFFICULTY_BEGINNER.labels,
        DIFFICULTY_INTERMEDIATE.name: DIFFICULTY_INTERMEDIATE.labels,
        DIFFICULTY_ADVANCED.name: DIFFICULTY_ADVANCED.labels,
    }

    rows = []

    for name, labels in groups.items():

        mask = df["labels"].map(
            lambda issue_labels: bool(labels.intersection(issue_labels or []))
        )

        rows.append(
            {
                "difficulty": name,
                "count": mask.sum(),
            }
        )

    return pd.DataFrame(rows)

def merged_pr_difficulty_distribution(
    df: pd.DataFrame,
) -> pd.DataFrame:

    groups = {
        DIFFICULTY_GOOD_FIRST_ISSUE.name: DIFFICULTY_GOOD_FIRST_ISSUE.labels,
        DIFFICULTY_BEGINNER.name: DIFFICULTY_BEGINNER.labels,
        DIFFICULTY_INTERMEDIATE.name: DIFFICULTY_INTERMEDIATE.labels,
        DIFFICULTY_ADVANCED.name: DIFFICULTY_ADVANCED.labels,
    }

    rows = []

    for name, labels in groups.items():

        mask = df["labels"].map(
            lambda l: bool(set(l) & labels)
        )

        rows.append(
            {
                "difficulty": name,
                "count": mask.sum(),
            }
        )

    return pd.DataFrame(rows)