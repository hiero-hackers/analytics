"""Analytics helpers for maintainer-pipeline role classification.

This module classifies contributor activity records, including both
pull request and issue activity, into governance roles and builds
aggregated pipeline tables.

The time views are one rule at four resolutions — a person counts for a bucket
if they were active anywhere in it — so the tabs zoom rather than disagree:
all time by year, the last year by month, the last month by week, the last week
by day. The repository view is the odd one out: it is a trailing activity
window rather than a bucket, because "which repos are alive now" is a different
question from "how has this moved".
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from hiero_analytics.analysis.dataframe_utils import records_to_dataframe
from hiero_analytics.data_sources.models import ContributorActivityRecord
from hiero_analytics.domain.bots import is_bot_login
from hiero_analytics.domain.repos import bare_repo

STAGE_COLUMNS = ["general_user", "triage", "committer", "maintainer"]

# For the yearly rollup: rank a person's roles so we can keep only their highest.
_STAGE_RANK = {stage: rank for rank, stage in enumerate(STAGE_COLUMNS)}

# Window of days used to determine "active" contributors.
ACTIVE_WINDOW_DAYS = 183

# Chart readability: how many recent buckets the fine-grained charts render.
# Full history is still written to CSV; only the rendered charts are trimmed,
# so the "By week"/"By month" views stay legible instead of becoming a wall of
# hundreds of bars.
RECENT_MONTHLY_BUCKETS = 12  # the "1 year" tab
RECENT_WEEKLY_BUCKETS = 5  # the "1 month" tab
RECENT_DAILY_BUCKETS = 7  # the "week" tab


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

        # Automation accounts (bots) aren't people in the maintainer pipeline.
        if not record.actor or is_bot_login(record.actor):
            return None

        repo_name = bare_repo(record.repo)
        actor_key = record.actor.strip().lower()
        role = repo_role_lookup.get(repo_name, {}).get(actor_key, "general_user")

        # Normalize to UTC so downstream window comparisons never hit
        # a naive-vs-aware mismatch.
        occurred_at = record.occurred_at
        occurred_at = occurred_at.replace(tzinfo=UTC) if occurred_at.tzinfo is None else occurred_at.astimezone(UTC)

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


def _counts_by_bucket(labelled: pd.DataFrame, bucket_col: str) -> pd.DataFrame:
    """Count distinct people per ``_bucket`` under their highest governance role.

    ``labelled`` must carry a ``_bucket`` column holding each row's
    chronologically-sortable period label. Each person is counted once per bucket,
    under the highest role they held in any repo that period, so the stacked bands
    are mutually exclusive and a bucket's total is the number of distinct active
    people.
    """
    highest = (
        labelled.assign(_rank=labelled["stage"].map(_STAGE_RANK))
        .sort_values("_rank")
        .drop_duplicates(subset=["_bucket", "actor"], keep="last")
    )

    counts = (
        highest.groupby(["_bucket", "stage"])["actor"]
        .nunique()
        .unstack(fill_value=0)
        .reindex(columns=STAGE_COLUMNS, fill_value=0)
        .reset_index()
        .rename(columns={"_bucket": bucket_col})
        .sort_values(bucket_col)
    )

    return counts.astype({column: int for column in STAGE_COLUMNS})


def build_maintainer_monthly_pipeline(stage_df: pd.DataFrame) -> pd.DataFrame:
    """Build monthly counts of distinct active people by their highest governance role.

    Each person is counted once per calendar month, under the highest role they held
    in any repo that month. Counts are strictly per-month (not a trailing window):
    someone active one month but not the next appears only in the month they were
    active, and the current, in-progress month reflects activity month-to-date.
    """
    if stage_df.empty:
        return pd.DataFrame(columns=["month", *STAGE_COLUMNS])

    # Vectorized 'YYYY-MM' label (occurred_at is UTC-normalized upstream).
    labelled = stage_df.assign(_bucket=stage_df["occurred_at"].dt.strftime("%Y-%m"))
    return _counts_by_bucket(labelled, "month")


def build_maintainer_weekly_pipeline(stage_df: pd.DataFrame) -> pd.DataFrame:
    """Build weekly counts of distinct active people by their highest governance role.

    Each person is counted once per ISO week (Mon–Sun), under the highest role they
    held in any repo that week. Counts are strictly per-week (not a trailing window),
    and the current, in-progress week reflects activity week-to-date.
    """
    if stage_df.empty:
        return pd.DataFrame(columns=["week", *STAGE_COLUMNS])

    # Vectorized 'YYYY-Www' ISO-week label.
    iso = stage_df["occurred_at"].dt.isocalendar()
    week_label = iso["year"].astype(str).str.zfill(4) + "-W" + iso["week"].astype(str).str.zfill(2)
    labelled = stage_df.assign(_bucket=week_label)
    return _counts_by_bucket(labelled, "week")


def build_maintainer_daily_pipeline(stage_df: pd.DataFrame) -> pd.DataFrame:
    """Build daily counts of distinct active people by their highest governance role.

    The finest bucket the tab row offers: the last week, one bar per day. Counts
    are strictly per-day, and today's bar reflects activity so far today.
    """
    if stage_df.empty:
        return pd.DataFrame(columns=["day", *STAGE_COLUMNS])

    labelled = stage_df.assign(_bucket=stage_df["occurred_at"].dt.strftime("%Y-%m-%d"))
    return _counts_by_bucket(labelled, "day")


def build_maintainer_yearly_pipeline(stage_df: pd.DataFrame) -> pd.DataFrame:
    """Build calendar-year counts of distinct active people by their highest role.

    Anyone active at any point in the year counts for that year — the same
    whole-bucket rule the daily, weekly, and monthly builders use, so every tab
    answers one question at a different resolution.

    Each person is counted once per year, under the highest role they held in any
    repo, so the stacked bands stay mutually exclusive and a year's total is the
    number of distinct active people.

    Past-year bars are stable across refreshes: a completed year's events cannot
    change, and nothing here depends on the run date. Only the current year moves,
    and only because the year is still in progress.
    """
    if stage_df.empty:
        return pd.DataFrame(columns=["year", *STAGE_COLUMNS])

    labelled = stage_df.assign(_bucket=stage_df["year"])
    return _counts_by_bucket(labelled, "year")


def build_maintainer_repo_pipeline(
    stage_df: pd.DataFrame,
    *,
    active_window_days: int = ACTIVE_WINDOW_DAYS,
    today: datetime | None = None,
) -> pd.DataFrame:
    """Build repository-level active contributor counts per governance stage.

    Only counts contributors active within the trailing ``active_window_days``
    window ending today, so the chart reflects current engagement rather than
    all-time history.
    """
    if stage_df.empty:
        return pd.DataFrame(columns=["repo", *STAGE_COLUMNS])

    cutoff = (today or datetime.now(UTC)) - timedelta(days=active_window_days)
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


def recent_buckets(pipeline_df: pd.DataFrame, max_buckets: int, *, newest_first: bool = False) -> pd.DataFrame:
    """Return the most recent ``max_buckets`` rows of a time-bucketed pipeline table.

    Monthly/weekly bucket labels ('YYYY-MM', 'YYYY-Www') sort lexicographically in
    chronological order, so the tail is the newest window. Used to keep the
    fine-grained charts legible while the full history stays in the CSV.

    With ``newest_first=True`` the rows are returned in reverse-chronological order,
    which places the latest bucket at the top of a horizontal bar chart. All rows
    are kept when the table is already within the limit or ``max_buckets`` is not
    positive.
    """
    if pipeline_df.empty:
        return pipeline_df.copy()

    # Sort by the bucket-label column (always first) so ``tail`` is genuinely the
    # newest window regardless of the caller's row order.
    bucket_col = pipeline_df.columns[0]
    result = pipeline_df.sort_values(bucket_col)

    if max_buckets > 0 and len(result) > max_buckets:
        result = result.tail(max_buckets)

    if newest_first:
        result = result.iloc[::-1]

    return result.reset_index(drop=True)
