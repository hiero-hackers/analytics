"""How long contributors wait: time-to-first-review and time-to-merge for PRs.

Pure transforms over the combined activity event frame
(:func:`~hiero_analytics.analysis.contributor_activity_profile.combined_activity_events`).
No data is fetched here; the activity events record PR creation, reviews, and merges.

Definitions:

- **Population** — merged pull requests with recorded creation and merge events.
  Open PRs and PRs closed without merging are excluded, so the results can
  understate waiting times. Bot activity is excluded by the activity frame.
- **First review** — the earliest review submitted by someone other than the
  author, between PR creation and merge. Review state is not inspected, so a
  comment-only review counts. The author's own reviews do not count.
- **Time-to-first-review** — first review minus PR creation, in wall-clock hours.
  It is missing when no qualifying review occurred before merge; those PRs still
  count in ``merged_prs`` and contribute to ``reviewed_share``.
- **Time-to-merge** — merge minus PR creation, in wall-clock hours. Weekends and
  time zones are not discounted.
- **Cohort** — contributor-history completeness is unavailable in the input
  events, so the analysis does not infer first-time versus established status.
  Every eligible PR is assigned to ``unknown``. The ``all`` summary includes
  all eligible PRs, so ``unknown`` and ``all`` rows contain the same metrics;
  ``unknown`` is not a separate contributor population.

Windows are ``(key, cutoff)`` pairs. A cutoff is the inclusive lower bound on
the PR merge time, or ``None`` for all recorded time. The analysis does not
read the current clock.

These are descriptive, aggregate metrics, not a measure or ranking of individual
reviewers.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import pandas as pd

Window = tuple[str, datetime | None]

ALL_COHORTS = "all"
UNKNOWN_COHORT = "unknown"
COHORTS = (ALL_COHORTS, UNKNOWN_COHORT)

# A 90th percentile of fewer values than this is just the maximum, so it is left
# empty rather than presented as a statistic.
P90_MIN_SAMPLE = 10

PR_RESPONSE_COLUMNS = [
    "repo",
    "pr_number",
    "author",
    "cohort",
    "created_at",
    "first_review_at",
    "merged_at",
    "hours_to_first_review",
    "hours_to_merge",
]

_STAT_COLUMNS = [
    "merged_prs",
    "reviewed_prs",
    "reviewed_share",
    "median_hours_to_first_review",
    "p90_hours_to_first_review",
    "median_hours_to_merge",
    "p90_hours_to_merge",
]
SUMMARY_COLUMNS = ["period", "cohort", *_STAT_COLUMNS]
REPO_SUMMARY_COLUMNS = ["repo", *SUMMARY_COLUMNS]
MONTHLY_COLUMNS = [
    "month",
    "cohort",
    "merged_prs",
    "reviewed_prs",
    "median_hours_to_first_review",
    "median_hours_to_merge",
]

_PR_KEY = ["repo", "target_number"]


def _empty_pr_frame() -> pd.DataFrame:
    """Return an empty PR response frame with the stable output schema."""
    return pd.DataFrame(columns=PR_RESPONSE_COLUMNS)


def _utc(values: pd.Series) -> pd.Series:
    """Convert timestamp values to UTC-aware pandas datetimes."""
    return pd.to_datetime(values, utc=True)


def pr_response_times(events: pd.DataFrame) -> pd.DataFrame:
    """Return one row per merged PR, with review and merge waits in hours.

    Contributor-history completeness is not available in the input events.
    Therefore every eligible PR receives the ``unknown`` cohort rather than
    inferring first-time or established-contributor status.

    Parameters
    ----------
    events
        The combined activity event frame (one row per tracked action).
    """
    if events.empty:
        return _empty_pr_frame()

    frame = events[events["occurred_at"].notna()].assign(occurred_at=lambda f: _utc(f["occurred_at"]))

    authored = frame[frame["activity_type"] == "authored_pull_request"]
    merged = frame[frame["activity_type"] == "merged_pull_request"]
    if authored.empty or merged.empty:
        return _empty_pr_frame()

    # Keep one creation record per PR.
    created = (
        authored.sort_values("occurred_at")
        .drop_duplicates(_PR_KEY)
        .rename(columns={"contributor": "author", "occurred_at": "created_at"})[[*_PR_KEY, "author", "created_at"]]
    )
    created["cohort"] = UNKNOWN_COHORT

    merges = (
        merged.sort_values("occurred_at")
        .drop_duplicates(_PR_KEY)
        .rename(columns={"occurred_at": "merged_at"})[[*_PR_KEY, "merged_at"]]
    )
    prs = created.merge(merges, on=_PR_KEY, how="inner")
    if prs.empty:
        return _empty_pr_frame()

    first_review = _first_review_by_others(frame, prs)
    prs = prs.merge(first_review, on=_PR_KEY, how="left")

    hour = pd.Timedelta(hours=1)
    prs["hours_to_first_review"] = (prs["first_review_at"] - prs["created_at"]) / hour
    prs["hours_to_merge"] = (prs["merged_at"] - prs["created_at"]) / hour

    # A merge recorded before creation is a data error, not a valid wait.
    prs = prs[prs["hours_to_merge"] >= 0]
    prs = prs.rename(columns={"target_number": "pr_number"})
    return prs[PR_RESPONSE_COLUMNS].sort_values(["repo", "pr_number"], ignore_index=True)


def _first_review_by_others(frame: pd.DataFrame, prs: pd.DataFrame) -> pd.DataFrame:
    """Find the earliest non-author review per PR, between creation and merge."""
    reviews = frame[frame["activity_type"] == "reviewed_pull_request"]
    reviews = reviews[reviews["contributor"] != reviews["target_author"]]
    bounds = prs[[*_PR_KEY, "created_at", "merged_at"]]
    reviews = reviews.merge(bounds, on=_PR_KEY, how="inner")
    reviews = reviews[
        (reviews["occurred_at"] >= reviews["created_at"]) & (reviews["occurred_at"] <= reviews["merged_at"])
    ]
    return (
        reviews.groupby(_PR_KEY, as_index=False)["occurred_at"].min().rename(columns={"occurred_at": "first_review_at"})
    )


def _percentile(values: pd.Series, q: float, *, min_sample: int = 1) -> float:
    """Calculate a rounded percentile when enough non-missing values exist."""
    values = values.dropna()
    return round(float(values.quantile(q)), 1) if len(values) >= min_sample else float("nan")


def _stats(prs: pd.DataFrame) -> dict[str, float | int]:
    """Calculate summary statistics for one group of merged PRs."""
    to_review = prs["hours_to_first_review"]
    to_merge = prs["hours_to_merge"]
    reviewed = int(to_review.notna().sum())
    total = len(prs)
    return {
        "merged_prs": total,
        "reviewed_prs": reviewed,
        "reviewed_share": round(reviewed / total * 100) if total else 0,
        "median_hours_to_first_review": _percentile(to_review, 0.5),
        "p90_hours_to_first_review": _percentile(to_review, 0.9, min_sample=P90_MIN_SAMPLE),
        "median_hours_to_merge": _percentile(to_merge, 0.5),
        "p90_hours_to_merge": _percentile(to_merge, 0.9, min_sample=P90_MIN_SAMPLE),
    }


def _cohort_slice(prs: pd.DataFrame, cohort: str) -> pd.DataFrame:
    """Select all PRs or the requested cohort."""
    return prs if cohort == ALL_COHORTS else prs[prs["cohort"] == cohort]


def responsiveness_summary(
    prs: pd.DataFrame,
    windows: Sequence[Window],
    *,
    by_repo: bool = False,
) -> pd.DataFrame:
    """Summarize review and merge waits per window and cohort.

    Every window and cohort gets a row, even when no PRs qualify. Empty groups
    receive zero counts and missing statistics. With ``by_repo=True``, only
    repositories represented in the PR data appear.
    """
    columns = REPO_SUMMARY_COLUMNS if by_repo else SUMMARY_COLUMNS
    if by_repo and prs.empty:
        return pd.DataFrame(columns=columns)

    groups = [(repo, group) for repo, group in prs.groupby("repo")] if by_repo else [(None, prs)]
    rows: list[dict[str, object]] = []
    for repo, group in groups:
        for key, cutoff in windows:
            in_window = group if cutoff is None else group[group["merged_at"] >= cutoff]
            for cohort in COHORTS:
                row: dict[str, object] = {
                    "period": key,
                    "cohort": cohort,
                    **_stats(_cohort_slice(in_window, cohort)),
                }
                rows.append({"repo": repo, **row} if by_repo else row)
    return pd.DataFrame(rows, columns=columns)


def monthly_responsiveness(prs: pd.DataFrame) -> pd.DataFrame:
    """Summarize review and merge waits by merge month and cohort.

    Months without PRs in a cohort are omitted instead of zero-filled.
    """
    if prs.empty:
        return pd.DataFrame(columns=MONTHLY_COLUMNS)

    month = prs["merged_at"].dt.strftime("%Y-%m")
    rows: list[dict[str, object]] = []
    for cohort in COHORTS:
        sliced = _cohort_slice(prs, cohort)
        for key, group in sliced.groupby(month.loc[sliced.index]):
            stats = _stats(group)
            rows.append(
                {
                    "month": key,
                    "cohort": cohort,
                    "merged_prs": stats["merged_prs"],
                    "reviewed_prs": stats["reviewed_prs"],
                    "median_hours_to_first_review": (stats["median_hours_to_first_review"]),
                    "median_hours_to_merge": stats["median_hours_to_merge"],
                }
            )
    return pd.DataFrame(rows, columns=MONTHLY_COLUMNS).sort_values(["month", "cohort"], ignore_index=True)
