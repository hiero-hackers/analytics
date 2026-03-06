from __future__ import annotations

from typing import Dict
import pandas as pd

from hiero_analytics.domain.labels import LabelSpec


def label_metrics(
    df: pd.DataFrame,
    label_spec: LabelSpec,
) -> Dict[str, pd.DataFrame]:
    """
    Compute metrics for a given label group.
    """

    if df.empty:
        return _empty_metrics()

    if "labels" not in df.columns:
        raise ValueError("DataFrame must contain a 'labels' column")

    labels = label_spec.labels

    mask = df["labels"].map(
        lambda issue_labels: bool(labels.intersection(issue_labels or []))
    )

    filtered = df[mask]

    if filtered.empty:
        return _empty_metrics()

    yearly = (
        filtered.groupby("year")
        .size()
        .reset_index(name="count")
        .sort_values("year")
    )

    yearly_by_repo = (
        filtered.groupby(["year", "repo"])
        .size()
        .reset_index(name="count")
        .sort_values(["year", "repo"])
    )

    total_by_repo = (
        filtered.groupby("repo")
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )

    return {
        "yearly": yearly,
        "yearly_by_repo": yearly_by_repo,
        "total_by_repo": total_by_repo,
    }


def _empty_metrics() -> Dict[str, pd.DataFrame]:

    return {
        "yearly": pd.DataFrame(columns=["year", "count"]),
        "yearly_by_repo": pd.DataFrame(columns=["year", "repo", "count"]),
        "total_by_repo": pd.DataFrame(columns=["repo", "count"]),
    }