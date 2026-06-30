"""Build the contributor-activity heatmap matrix (weighted monthly activity).

The ranked, score-based companion to the descriptive profiles in
``contributor_activity_profile``. Activity is weighted by action type and bucketed
by month; only activity within the displayed window is scored, so the top-N
selection, the "activity score" and the month columns all agree — the busiest
*recent* contributors rise to the top. Automation accounts are excluded.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from hiero_analytics.config.analysis import ACTIVITY_WEIGHTS, HEATMAP_MONTHS, HEATMAP_TOP_ROWS
from hiero_analytics.data_sources.governance_config import ROLE_PRIORITY
from hiero_analytics.domain.bots import is_bot_login
from hiero_analytics.domain.repos import bare_repo

ROLE_LABELS = {
    "general_user": "General User",
    "triage": "Triage",
    "committer": "Committer",
    "maintainer": "Maintainer",
}

# Normalized activity type -> heatmap action bucket (the weights live in config).
ACTIVITY_TYPE_TO_ACTION = {
    "authored_issue": "issues",
    "reviewed_pull_request": "reviews",
    "authored_pull_request": "prs created",
    "merged_pull_request": "prs merged",
}

_META_COLUMNS = ("contributor name", "role", "activity score")


def _as_utc(value: datetime) -> datetime:
    """Normalize datetimes to UTC for monthly grouping."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _month_key(value: datetime) -> str:
    """Return a stable month bucket label for a timestamp."""
    return _as_utc(value).strftime("%Y-%m")


def _recent_month_keys(months_back: int) -> list[str]:
    """Return the most recent month labels, oldest first."""
    current_month = pd.Period(pd.Timestamp.now(tz="UTC"), freq="M")
    return [str(period) for period in pd.period_range(end=current_month, periods=months_back, freq="M")]


def _activity_action(activity_type: str) -> str | None:
    """Map a normalized activity event to a heatmap action bucket."""
    return ACTIVITY_TYPE_TO_ACTION.get(activity_type)


def _build_activity_rollup(
    records,
    repo_role_lookup: dict[str, dict[str, str]],
) -> dict[str, dict[str, object]]:
    """Aggregate contributor actions into a per-person rollup (bots excluded)."""
    per_contributor: dict[str, dict[str, object]] = defaultdict(
        lambda: {
            "contributor name": "",
            "role key": "general_user",
            "role priority": ROLE_PRIORITY["general_user"],
            "weighted activity score": 0,
            "monthly scores": defaultdict(int),
        }
    )

    for record in records:
        actor = (record.actor or "").strip()
        action = _activity_action(record.activity_type)
        if not actor or action is None or record.occurred_at is None or is_bot_login(actor):
            continue

        actor_key = actor.lower()
        repo_name = bare_repo(record.repo)
        detected_role = repo_role_lookup.get(repo_name, {}).get(actor_key, "general_user")

        row = per_contributor[actor_key]
        row["contributor name"] = actor

        current_role = str(row["role key"])
        if ROLE_PRIORITY[detected_role] > ROLE_PRIORITY[current_role]:
            row["role key"] = detected_role
            row["role priority"] = ROLE_PRIORITY[detected_role]

        row["weighted activity score"] = int(row["weighted activity score"]) + ACTIVITY_WEIGHTS[action]
        row["monthly scores"][_month_key(record.occurred_at)] += ACTIVITY_WEIGHTS[action]

    return per_contributor


def build_activity_heatmap_dataframe(
    records,
    repo_role_lookup: dict[str, dict[str, str]],
    *,
    months_back: int = HEATMAP_MONTHS,
) -> pd.DataFrame:
    """Build a contributor-by-month activity matrix, busiest recent contributors first.

    Only activity within the displayed window (the most recent ``months_back``
    months) is scored, so the score, the top-N selection and the month columns all
    agree. Rows are sorted by total weighted activity (descending).
    """
    month_columns = _recent_month_keys(months_back)
    window = set(month_columns)
    windowed = [
        record
        for record in records
        if record.occurred_at is not None and _month_key(record.occurred_at) in window
    ]
    rollup = _build_activity_rollup(windowed, repo_role_lookup)

    rows: list[dict[str, object]] = []
    for item in rollup.values():
        monthly_scores = item["monthly scores"]
        row = {
            "contributor name": item["contributor name"],
            "role": ROLE_LABELS.get(str(item["role key"]), "General User"),
            "activity score": int(item["weighted activity score"]),
        }
        for month in month_columns:
            row[month] = int(monthly_scores.get(month, 0))
        rows.append(row)

    columns = [*_META_COLUMNS, *month_columns]
    if not rows:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(rows)
    return df.sort_values(by=["activity score", "contributor name"], ascending=[False, True]).reset_index(drop=True)


def heatmap_chart_data(
    heatmap_df: pd.DataFrame,
    *,
    top_rows: int = HEATMAP_TOP_ROWS,
) -> tuple[np.ndarray, list[str], list[str]] | None:
    """Top-N rows as ``(values, row_labels, col_labels)`` for plotting, or None if empty."""
    if heatmap_df.empty:
        return None
    month_columns = [column for column in heatmap_df.columns if column not in set(_META_COLUMNS)]
    chart_df = heatmap_df.head(top_rows)
    if chart_df.empty:
        return None
    values = chart_df[month_columns].to_numpy(dtype=float)
    return values, chart_df["contributor name"].tolist(), month_columns
