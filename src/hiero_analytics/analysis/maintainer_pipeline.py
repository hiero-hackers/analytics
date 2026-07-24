"""Analytics helpers for maintainer-pipeline role classification.

This module classifies contributor activity records, including both
pull request and issue activity, into governance roles and builds
aggregated pipeline tables for yearly, monthly, weekly, and
repository-level views.
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
RECENT_MONTHLY_BUCKETS = 24
RECENT_WEEKLY_BUCKETS = 26


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


def _active_window_for_year(
    year: int, today: datetime, window_days: int = ACTIVE_WINDOW_DAYS
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


def build_maintainer_yearly_pipeline(
    stage_df: pd.DataFrame,
    *,
    active_window_days: int = ACTIVE_WINDOW_DAYS,
    today: datetime | None = None,
) -> pd.DataFrame:
    """Build yearly counts of distinct active people by their highest governance role.

    Only counts contributors active in the last 6 months of each year (past years use
    a fixed H2 window, stable across refreshes; the current year uses a full trailing
    ``active_window_days``-day window from today, which early in the year reaches into
    the previous December — those events count toward the current bar). Each person is
    counted once per year, under the highest role they held in any repo, so the bands
    are mutually exclusive and a year's total is the number of distinct active people.
    """
    if stage_df.empty:
        return pd.DataFrame(columns=["year", *STAGE_COLUMNS])

    today = today or datetime.now(UTC)
    years = stage_df["year"].unique()

    filtered_frames: list[pd.DataFrame] = []
    for year in sorted(years):
        window_start, window_end = _active_window_for_year(year, today, active_window_days)
        mask = (stage_df["occurred_at"] >= window_start) & (stage_df["occurred_at"] <= window_end)
        if year < today.year:
            filtered_frames.append(stage_df.loc[mask & (stage_df["year"] == year)])
        else:
            # The current bar is a full trailing window, as the chart note states.
            # Early in the year it reaches into last December; those events are
            # relabelled so they count toward the current bar, not last year's.
            filtered_frames.append(stage_df.loc[mask].assign(year=year))

    active_df = pd.concat(filtered_frames, ignore_index=True) if filtered_frames else stage_df.iloc[0:0]

    # One row per (year, actor) at their highest role — the shared bucket counter
    # keeps the stacked bands mutually exclusive.
    labelled = active_df.assign(_bucket=active_df["year"])
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
