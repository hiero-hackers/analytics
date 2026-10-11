"""How long contributors wait: time-to-first-review and time-to-merge for pull requests.

Pure transforms over the combined activity event frame
(:func:`~hiero_analytics.analysis.contributor_activity_profile.combined_activity_events`).
Nothing is fetched: the activity events already carry when each PR was opened
(``authored_pull_request``), when each review was submitted
(``reviewed_pull_request``) and when it was merged (``merged_pull_request``).

Definitions (state them wherever the numbers are shown):

- **Population** — merged pull requests whose creation and merge were both
  recorded. A PR that was closed unmerged, or is still open, has no merge event
  and is excluded, so waits are understated: the PRs that waited longest are the
  likeliest to be abandoned. PRs authored or merged by automation accounts are
  excluded too (the activity frame drops bots), as are PRs whose merge event is
  credited to a bot.
- **First review** — the earliest review submitted on the PR by someone other
  than its author, at or before the merge. Review state is not inspected, so a
  comment-only review counts as a response; the author replying in a review
  thread does not. Reviews by bots are not in the frame.
- **Time-to-first-review** — first review minus PR creation, in hours. Missing
  (``NaN``) when nobody else reviewed the PR before it merged; those PRs still
  count in ``merged_prs`` and are what ``reviewed_share`` measures.
- **Time-to-merge** — merge minus PR creation, in hours. Wall-clock time:
  weekends and time zones are not discounted.
- **Cohort** — ``first_prs`` when the PR is among its author's first
  ``newcomer_max_prs`` PRs in the frame (counting every authored PR, merged or
  not), ``later_prs`` otherwise. This follows each person's own early PRs even
  if they stayed on, rather than labelling only people who never returned.

Windows are ``(key, cutoff)`` pairs like the entity-activity tables: ``cutoff``
is the inclusive lower bound on the **merge** time, or ``None`` for all recorded
time. Nothing here reads the clock.

This is descriptive, repo- and cohort-level information, not a measure of any
individual reviewer: it never ranks people.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import pandas as pd

Window = tuple[str, datetime | None]

ALL_COHORTS = "all"
FIRST_PRS = "first_prs"
LATER_PRS = "later_prs"
COHORTS = (ALL_COHORTS, FIRST_PRS, LATER_PRS)

# A person's first PRs, matching the "newcomer" heuristic the contributor
# profiles already use (``build_contributor_profiles``).
DEFAULT_NEWCOMER_MAX_PRS = 2

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
    return pd.DataFrame(columns=PR_RESPONSE_COLUMNS)


def _utc(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, utc=True)


def pr_response_times(
    events: pd.DataFrame,
    *,
    newcomer_max_prs: int = DEFAULT_NEWCOMER_MAX_PRS,
) -> pd.DataFrame:
    """One row per merged pull request, with its waits in hours.

    Parameters
    ----------
    events
        The combined activity event frame (one row per tracked action).
    newcomer_max_prs
        A PR is in the ``first_prs`` cohort when it is among its author's first
        this-many PRs in ``events`` (earliest first).

    Returns:
    -------
    pd.DataFrame
        ``PR_RESPONSE_COLUMNS``; empty (with that schema) when there is no
        merged PR with both a recorded creation and a recorded merge.
    """
    if events.empty:
        return _empty_pr_frame()

    frame = events[events["occurred_at"].notna()].assign(occurred_at=lambda f: _utc(f["occurred_at"]))

    authored = frame[frame["activity_type"] == "authored_pull_request"]
    merged = frame[frame["activity_type"] == "merged_pull_request"]
    if authored.empty or merged.empty:
        return _empty_pr_frame()

    # One row per PR. A PR should appear once; keeping the earliest event makes a
    # duplicated record harmless rather than double-counted.
    created = (
        authored.sort_values("occurred_at")
        .drop_duplicates(_PR_KEY)
        .rename(columns={"contributor": "author", "occurred_at": "created_at"})[[*_PR_KEY, "author", "created_at"]]
    )
    created["pr_order"] = created.groupby("author")["created_at"].rank(method="first")
    created["cohort"] = created["pr_order"].le(newcomer_max_prs).map({True: FIRST_PRS, False: LATER_PRS})

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

    # A merge recorded before its own creation is a data error, not a wait.
    prs = prs[prs["hours_to_merge"] >= 0]
    prs = prs.rename(columns={"target_number": "pr_number"})
    return prs[PR_RESPONSE_COLUMNS].sort_values(["repo", "pr_number"], ignore_index=True)


def _first_review_by_others(frame: pd.DataFrame, prs: pd.DataFrame) -> pd.DataFrame:
    """Earliest non-author review per PR, between its creation and its merge."""
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
    values = values.dropna()
    return round(float(values.quantile(q)), 1) if len(values) >= min_sample else float("nan")


def _stats(prs: pd.DataFrame) -> dict[str, float | int]:
    """The summary statistics for one group of merged PRs."""
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
    return prs if cohort == ALL_COHORTS else prs[prs["cohort"] == cohort]


def responsiveness_summary(
    prs: pd.DataFrame,
    windows: Sequence[Window],
    *,
    by_repo: bool = False,
) -> pd.DataFrame:
    """Median and 90th-percentile waits per window and cohort, org-wide or per repo.

    Every window and cohort gets a row (zero PRs gives ``merged_prs`` 0 and empty
    statistics) so a chart or table never has to guess whether a cell is missing
    or zero. A repo appears only if it has at least one merged PR in the data.
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
                row: dict[str, object] = {"period": key, "cohort": cohort, **_stats(_cohort_slice(in_window, cohort))}
                rows.append({"repo": repo, **row} if by_repo else row)
    return pd.DataFrame(rows, columns=columns)


def monthly_responsiveness(prs: pd.DataFrame) -> pd.DataFrame:
    """Median waits by the month PRs were merged, per cohort, for a trend line.

    Months with no merged PR in a cohort are omitted rather than zero-filled: an
    empty month has no median, and a zero would read as "instant".
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
                    "median_hours_to_first_review": stats["median_hours_to_first_review"],
                    "median_hours_to_merge": stats["median_hours_to_merge"],
                }
            )
    return pd.DataFrame(rows, columns=MONTHLY_COLUMNS).sort_values(["month", "cohort"], ignore_index=True)
