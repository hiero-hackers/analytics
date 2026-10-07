"""Per-repository and per-contributor activity for the dashboard's detail views.

Pure transforms over the combined activity event frame
(:func:`~hiero_analytics.analysis.contributor_activity_profile.combined_activity_events`):
one row per tracked action — a pull request authored, a review submitted, a pull
request merged (credited to whoever merged it), an issue opened, or a label
applied. Every count here is a count of those events, with the same definitions
the contributor profiles use, so the detail views agree with the Contributors tab.

Each table is computed once per window from the events themselves (never by
summing per-contributor or org-wide summary rows), so a repository's
*active contributors* in the last week is the number of distinct people with a
tracked action in that repository in that week, not a sum of overlapping counts.

Windows are ``(key, cutoff)`` pairs: ``cutoff`` is the inclusive lower bound, or
``None`` for all recorded time. The caller decides the windows and the moment
they end; nothing here reads the clock.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import pandas as pd

from hiero_analytics.analysis.contributor_activity_profile import CONTRIB_COUNT_FIELDS

# Which tracked activity type each count field counts (the profile definitions).
COUNT_OF_ACTIVITY: dict[str, str] = {
    "authored_pull_request": "prs_opened",
    "reviewed_pull_request": "reviews_given",
    "merged_pull_request": "merges_done",
    "authored_issue": "issues_opened",
    "labeled_issue": "labels_applied",
}

# The three neutral work families, as sums of the count fields.
FAMILY_FIELDS: dict[str, tuple[str, ...]] = {
    "building_and_fixing": ("prs_opened",),
    "reviewing_and_guiding": ("reviews_given", "merges_done"),
    "organizing_and_answering": ("issues_opened", "labels_applied"),
}
SHARE_OF_FAMILY = {
    "building_and_fixing": "building_share",
    "reviewing_and_guiding": "reviewing_share",
    "organizing_and_answering": "organizing_share",
}

Window = tuple[str, datetime | None]

REPO_ACTIVITY_COLUMNS = [
    "repo",
    "period",
    *CONTRIB_COUNT_FIELDS,
    "total_actions",
    "active_contributors",
    "first_active",
    "last_active",
]
CONTRIBUTOR_ACTIVITY_COLUMNS = [
    "contributor",
    "period",
    *CONTRIB_COUNT_FIELDS,
    "total_actions",
    "repos_touched",
    *FAMILY_FIELDS,
    *SHARE_OF_FAMILY.values(),
    "first_active",
    "last_active",
]
PAIR_ACTIVITY_COLUMNS = [
    "repo",
    "contributor",
    "period",
    *CONTRIB_COUNT_FIELDS,
    "total_actions",
    *SHARE_OF_FAMILY.values(),
    "first_active",
    "last_active",
]
MONTHLY_COLUMNS = ["month", *CONTRIB_COUNT_FIELDS]


def _counted(events: pd.DataFrame) -> pd.DataFrame:
    """The events that count toward a field, tagged with that field.

    Activity types outside the five tracked ones (none today) are dropped rather
    than silently folded into a total.
    """
    frame = events.assign(field=events["activity_type"].map(COUNT_OF_ACTIVITY))
    return frame[frame["field"].notna() & frame["occurred_at"].notna()]


def _in_window(events: pd.DataFrame, cutoff: datetime | None) -> pd.DataFrame:
    return events if cutoff is None else events[events["occurred_at"] >= cutoff]


def _field_counts(events: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """One row per key combination with an integer column per count field."""
    counts = events.groupby([*keys, "field"]).size().unstack("field", fill_value=0)
    counts = counts.reindex(columns=list(CONTRIB_COUNT_FIELDS), fill_value=0).astype(int)
    counts["total_actions"] = counts[list(CONTRIB_COUNT_FIELDS)].sum(axis=1)
    return counts


def _span(events: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    grouped = events.groupby(keys)["occurred_at"]
    return pd.DataFrame({"first_active": grouped.min(), "last_active": grouped.max()})


def _share(part: pd.Series, whole: pd.Series) -> pd.Series:
    """Integer percentages, 0 where the whole is 0 (matches the profile tables)."""
    return (part / whole.where(whole > 0) * 100).round().fillna(0).astype(int)


def _add_families(frame: pd.DataFrame, *, keep_counts: bool) -> pd.DataFrame:
    for family, fields in FAMILY_FIELDS.items():
        total = frame[list(fields)].sum(axis=1)
        if keep_counts:
            frame[family] = total
        frame[SHARE_OF_FAMILY[family]] = _share(total, frame["total_actions"])
    return frame


def _per_window(
    events: pd.DataFrame,
    windows: Sequence[Window],
    columns: list[str],
    build,
) -> pd.DataFrame:
    """Concatenate ``build(window_events)`` for each window, tagged with its key."""
    counted = _counted(events)
    frames = []
    for key, cutoff in windows:
        scoped = _in_window(counted, cutoff)
        if scoped.empty:
            continue
        frame = build(scoped)
        frame.insert(0, "period", key)
        frames.append(frame.reset_index())
    if not frames:
        return pd.DataFrame(columns=columns)
    return pd.concat(frames, ignore_index=True)[columns]


def repo_activity(events: pd.DataFrame, windows: Sequence[Window]) -> pd.DataFrame:
    """Each repository's tracked actions and distinct active contributors per window.

    A repository with no tracked action in a window has no row for it; the
    detail view reads a missing row as zero activity.
    """

    def build(scoped: pd.DataFrame) -> pd.DataFrame:
        frame = _field_counts(scoped, ["repo"])
        frame["active_contributors"] = scoped.groupby("repo")["contributor"].nunique()
        return frame.join(_span(scoped, ["repo"]))

    return _per_window(events, windows, REPO_ACTIVITY_COLUMNS, build)


def contributor_activity(events: pd.DataFrame, windows: Sequence[Window]) -> pd.DataFrame:
    """Each contributor's tracked actions, work mix and repositories touched per window."""

    def build(scoped: pd.DataFrame) -> pd.DataFrame:
        frame = _field_counts(scoped, ["contributor"])
        frame["repos_touched"] = scoped.groupby("contributor")["repo"].nunique()
        frame = _add_families(frame, keep_counts=True)
        return frame.join(_span(scoped, ["contributor"]))

    return _per_window(events, windows, CONTRIBUTOR_ACTIVITY_COLUMNS, build)


def repo_contributor_activity(events: pd.DataFrame, windows: Sequence[Window]) -> pd.DataFrame:
    """Each (repository, contributor) pair's tracked actions and work mix per window.

    The one table behind both a repository's contributor list and a
    contributor's per-repository breakdown, so the two can never disagree.
    """

    def build(scoped: pd.DataFrame) -> pd.DataFrame:
        frame = _add_families(_field_counts(scoped, ["repo", "contributor"]), keep_counts=False)
        return frame.join(_span(scoped, ["repo", "contributor"]))

    return _per_window(events, windows, PAIR_ACTIVITY_COLUMNS, build)


def monthly_activity(events: pd.DataFrame, key: str) -> pd.DataFrame:
    """Tracked actions per calendar month (UTC) per ``key`` (``repo`` or ``contributor``).

    Months without activity are absent; the chart export completes the calendar.
    """
    counted = _counted(events)
    columns = [key, *MONTHLY_COLUMNS]
    if counted.empty:
        return pd.DataFrame(columns=columns)
    frame = _field_counts(counted, [key, "month"]).drop(columns="total_actions").reset_index()
    return frame.sort_values([key, "month"], ignore_index=True)[columns]
