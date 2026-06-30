"""Analytics helpers for maintainer-pipeline role classification.

This module classifies contributor activity records, including both
pull request and issue activity, into governance roles and builds
aggregated pipeline tables for yearly and repository-level views.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from hiero_analytics.analysis.dataframe_utils import records_to_dataframe
from hiero_analytics.data_sources.models import ContributorActivityRecord

STAGE_COLUMNS = ["general_user", "triage", "committer", "maintainer"]

_MAINTAINER_ACTIVITY_TYPES = {
    "authored_issue",
    "authored_pull_request",
    "reviewed_pull_request",
    "merged_pull_request",
}


def activity_to_role_dataframe(
    records: list[ContributorActivityRecord],
    repo_role_lookup: dict[str, dict[str, str]],
) -> pd.DataFrame:
    """Classify each contributor activity record by governance role.

    Includes ``occurred_at`` so downstream aggregations can apply per-year
    activity windows without re-fetching.
    """

    def to_row(record: ContributorActivityRecord) -> dict[str, object] | None:
        if record.activity_type not in _MAINTAINER_ACTIVITY_TYPES:
            return None

        repo_name = record.repo.split("/")[-1]
        actor_key = record.actor.strip().lower()
        role = repo_role_lookup.get(repo_name, {}).get(actor_key, "general_user")

        # Normalize to UTC so downstream window comparisons never hit
        # a naive-vs-aware mismatch.
        occurred_at = record.occurred_at
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=UTC)
        else:
            occurred_at = occurred_at.astimezone(UTC)

        return {
            "repo": repo_name,
            "actor": record.actor,
            "occurred_at": occurred_at,
            "year": occurred_at.year,
            "stage": role,
        }

    return records_to_dataframe(
        records,
        to_row,
        ["repo", "actor", "occurred_at", "year", "stage"],
    )


def _active_window_for_year(
    year: int, today: datetime, window_days: int = 183
) -> tuple[datetime, datetime]:
    """Return the (start, end) activity window for a given year.

    Completed years use a fixed H2 window (Jul 1 – Dec 31) so historical
    counts never change on refresh.  The current year uses a trailing
    ``window_days``-day window ending today.
    """
    if year < today.year:
        # Past year: fixed last-6-months window, immune to re-run date.
        window_start = datetime(year, 7, 1, tzinfo=UTC)
        window_end = datetime(year, 12, 31, 23, 59, 59, tzinfo=UTC)
    else:
        # Current year: trailing window from today.
        window_end = today
        window_start = today - timedelta(days=window_days)

    return window_start, window_end


def build_maintainer_yearly_pipeline(
    stage_df: pd.DataFrame,
    *,
    active_window_days: int = 183,
) -> pd.DataFrame:
    """Build yearly contributor counts per PR and issue activity stage.

    Only counts contributors active in the last 6 months of each year.
    Past years use a fixed H2 window (stable across refreshes); the current
    year uses a trailing ``active_window_days``-day window from today.
    """
    if stage_df.empty:
        return pd.DataFrame(columns=["year", *STAGE_COLUMNS])

    today = datetime.now(UTC)
    years = stage_df["year"].unique()

    filtered_frames: list[pd.DataFrame] = []
    for year in sorted(years):
        window_start, window_end = _active_window_for_year(year, today, active_window_days)
        mask = (
            (stage_df["year"] == year)
            & (stage_df["occurred_at"] >= window_start)
            & (stage_df["occurred_at"] <= window_end)
        )
        filtered_frames.append(stage_df.loc[mask])

    active_df = pd.concat(filtered_frames, ignore_index=True) if filtered_frames else stage_df.iloc[0:0]

    yearly = (
        active_df.groupby(["year", "stage"])["actor"]
        .nunique()
        .unstack(fill_value=0)
        .reindex(columns=STAGE_COLUMNS, fill_value=0)
        .reset_index()
        .sort_values("year")
    )

    return yearly.astype({column: int for column in STAGE_COLUMNS})


def build_maintainer_repo_pipeline(
    stage_df: pd.DataFrame,
    *,
    active_window_days: int = 183,
) -> pd.DataFrame:
    """Build repository-level active contributor counts per governance stage.

    Only counts contributors active within the trailing ``active_window_days``
    window ending today, so the chart reflects current engagement rather than
    all-time history.
    """
    if stage_df.empty:
        return pd.DataFrame(columns=["repo", *STAGE_COLUMNS])

    cutoff = datetime.now(UTC) - timedelta(days=active_window_days)
    active_df = stage_df[stage_df["occurred_at"] >= cutoff]

    if active_df.empty:
        return pd.DataFrame(columns=["repo", *STAGE_COLUMNS])

    by_repo = (
        active_df.groupby(["repo", "stage"])["actor"]
        .nunique()
        .unstack(fill_value=0)
        .reindex(columns=STAGE_COLUMNS, fill_value=0)
        .reset_index()
    )

    by_repo["total"] = by_repo[STAGE_COLUMNS].sum(axis=1)
    by_repo = by_repo.sort_values("total", ascending=False).drop(columns=["total"])

    return by_repo.astype({column: int for column in STAGE_COLUMNS})


def collapse_repo_pipeline_tail(repo_df: pd.DataFrame, max_repos: int) -> pd.DataFrame:
    """Return a chart-friendly repo table with the long tail aggregated."""
    if repo_df.empty or max_repos <= 0 or len(repo_df) <= max_repos:
        return repo_df.copy()

    head_count = max_repos - 1
    if head_count <= 0:
        return repo_df.copy()

    head = repo_df.head(head_count).copy()
    tail = repo_df.iloc[head_count:]

    other_totals = {column: int(tail[column].sum()) for column in STAGE_COLUMNS}
    other_row = pd.DataFrame(
        [
            {
                "repo": f"Other Repos ({len(tail)})",
                **other_totals,
            }
        ]
    )

    return pd.concat([head, other_row], ignore_index=True)
