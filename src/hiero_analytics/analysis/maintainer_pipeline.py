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

from datetime import UTC, date, datetime, timedelta

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
    active_window_days: int | None = ACTIVE_WINDOW_DAYS,
    today: datetime | None = None,
) -> pd.DataFrame:
    """Build repository-level active contributor counts per governance stage.

    Counts contributors active within the trailing ``active_window_days``
    window ending today; ``None`` means all recorded time, so the same builder
    serves every span tab of the by-repository card.
    """
    if stage_df.empty:
        return pd.DataFrame(columns=["repo", *STAGE_COLUMNS])

    if active_window_days is None:
        active_df = stage_df
    else:
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


def last_calendar_buckets(now: datetime, count: int, freq: str) -> list[str]:
    """The last ``count`` calendar bucket labels ending at ``now``'s bucket, oldest first.

    ``freq`` is ``"day"`` ('YYYY-MM-DD'), ``"week"`` (ISO 'YYYY-Www'), or
    ``"month"`` ('YYYY-MM') — the label formats the pipeline builders emit.
    """
    if freq == "day":
        return [(now.date() - timedelta(days=i)).strftime("%Y-%m-%d") for i in reversed(range(count))]
    if freq == "week":
        monday = now.date() - timedelta(days=now.date().weekday())
        weeks = [(monday - timedelta(weeks=i)).isocalendar() for i in reversed(range(count))]
        return [f"{iso.year:04d}-W{iso.week:02d}" for iso in weeks]
    if freq == "month":
        year, month = now.year, now.month
        labels = []
        for _ in range(count):
            labels.append(f"{year:04d}-{month:02d}")
            year, month = (year - 1, 12) if month == 1 else (year, month - 1)
        return list(reversed(labels))
    raise ValueError(f"unknown bucket frequency: {freq!r}")


def calendar_recent_buckets(pipeline_df: pd.DataFrame, labels: list[str]) -> pd.DataFrame:
    """The chart window as complete calendar buckets: exactly ``labels``, zero-filled.

    Unlike taking the tail of the *populated* buckets, a span with no activity
    stays in the window as a zero bar — so a chart labelled "1 month" covers
    exactly the last month's calendar weeks and never stretches back to older
    activity to fill its bar budget. Full history stays in the CSV; only the
    rendered chart is windowed. An empty input stays empty so the plotting
    layer's skip-empty behaviour is preserved.
    """
    if pipeline_df.empty:
        return pipeline_df.copy()

    bucket_col = pipeline_df.columns[0]
    count_cols = [column for column in pipeline_df.columns if column != bucket_col]
    return (
        pipeline_df.set_index(bucket_col)
        .reindex(labels, fill_value=0)
        .reset_index(names=bucket_col)
        .astype({column: int for column in count_cols})
    )


def humanize_month_label(bucket: str) -> str:
    """``2026-07`` -> ``Jul 2026``. Chart display only; CSVs keep sortable keys."""
    try:
        return datetime.strptime(bucket, "%Y-%m").replace(tzinfo=UTC).strftime("%b %Y")
    except ValueError:
        return bucket


def humanize_week_label(bucket: str) -> str:
    """``2026-W32`` -> ``w/c 3 Aug 2026``, the week's Monday.

    A date a human can place, unlike an ISO week number. Chart display only.
    """
    try:
        year, week = bucket.split("-W")
        monday = date.fromisocalendar(int(year), int(week), 1)
    except (ValueError, AttributeError):
        return bucket
    return f"w/c {monday.day} {monday.strftime('%b %Y')}"


def humanize_day_label(bucket: str) -> str:
    """``2026-08-05`` -> ``Wed 5 Aug 2026``.

    The weekday is what makes a weekend dip readable at a glance. Chart
    display only.
    """
    try:
        day = datetime.strptime(bucket, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return bucket
    return f"{day.strftime('%a')} {day.day} {day.strftime('%b %Y')}"
