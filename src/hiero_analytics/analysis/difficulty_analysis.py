"""Difficulty classification and window-selection helpers for issue analytics."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from hiero_analytics.analysis.timeseries import (
    TIMELINE_EVENT_ORDER,
    normalize_datetime,
)
from hiero_analytics.data_sources.models import IssueRecord, IssueTimelineEventRecord
from hiero_analytics.domain.labels import (
    DIFFICULTY_LEVELS,
    UNKNOWN_DIFFICULTY,
    LabelSpec,
)


def assign_difficulty(
    labels,
    specs: tuple[LabelSpec, ...] = DIFFICULTY_LEVELS,
) -> str:
    """Return the first matching difficulty label for an issue, or Unknown.

    ``labels`` may be any iterable of label names (or ``None``); matching is
    delegated to each spec and is case-insensitive.  This is the single
    per-issue difficulty classifier used across the analytics pipelines.
    """
    label_set = set(labels or [])
    for spec in specs:
        if spec.matches(label_set):
            return spec.name
    return UNKNOWN_DIFFICULTY


def build_difficulty_dataframe(
    df: pd.DataFrame,
    specs: tuple[LabelSpec, ...] = DIFFICULTY_LEVELS,
    *,
    state: str | None = None,
) -> pd.DataFrame:
    """Aggregate issue counts per difficulty level, including an Unknown bucket.

    Each issue is assigned to exactly one bucket via :func:`assign_difficulty`
    (the first matching spec wins), so counts sum to the number of issues.
    The result has one row per spec in ``specs`` order followed by an
    ``Unknown`` row, with zero-filled counts for absent buckets.

    Parameters
    ----------
    df
        Issue dataframe containing a ``labels`` column (and a ``state`` column
        if ``state`` filtering is requested).
    specs
        Ordered difficulty specifications. Defaults to ``DIFFICULTY_LEVELS``.
    state
        Optional issue state filter (e.g. ``"open"``); when provided, only
        rows whose ``state`` column matches are aggregated.

    Returns:
    -------
    pd.DataFrame
        DataFrame with ``difficulty`` and ``count`` columns.
    """
    if state:
        df = df[df["state"] == state]

    assigned = df["labels"].apply(lambda labels: assign_difficulty(labels, specs))
    counts = assigned.value_counts()

    rows = [{"difficulty": spec.name, "count": int(counts.get(spec.name, 0))} for spec in specs]
    rows.append({"difficulty": UNKNOWN_DIFFICULTY, "count": int(counts.get(UNKNOWN_DIFFICULTY, 0))})

    return pd.DataFrame(rows)


def issues_labeled_since(
    issues: list[IssueRecord],
    timeline_events: list[IssueTimelineEventRecord],
    cutoff: datetime,
    difficulty_specs: tuple[LabelSpec, ...],
) -> set[tuple[str, int]]:
    """Return (repo, number) pairs for issues with an active difficulty label applied since cutoff.

    An issue qualifies when a difficulty label was added within the window
    and has not been subsequently removed.  Issues created after the cutoff
    that already carry a difficulty label are included as a fallback for
    cases where the label was applied at creation time (e.g. via an issue
    template) and no separate ``labeled`` event is recorded.
    """
    difficulty_label_names: set[str] = set()
    for spec in difficulty_specs:
        difficulty_label_names |= spec.labels

    # Precompute the set of issue keys we care about so we can skip
    # repository-wide events for issues outside the fetched set (e.g.
    # closed issues or issues not matching the query).
    issue_key_set = {(issue.repo, issue.number) for issue in issues}

    # Sort events chronologically with a stable tie-breaker to handle
    # unordered results from concurrent per-repo REST API fetches.
    sorted_events = sorted(
        timeline_events,
        key=lambda event: (
            normalize_datetime(event.occurred_at),
            TIMELINE_EVENT_ORDER.get(event.event_type, 99),
        ),
    )

    # Track active difficulty labels per issue *and* the time each became
    # active.  Keyed by (repo, issue_number, label) so removing one difficulty
    # label does not erase the record of a different one.  We record the
    # application time so the cutoff can be applied here rather than relying on
    # the caller having pre-filtered events to the window: the timeline source
    # (GraphQL ``timelineItems``) returns full history, so an issue labeled long
    # ago is still "active" and must be excluded explicitly.
    cutoff = normalize_datetime(cutoff)
    active_since: dict[tuple[str, int, str], datetime | None] = {}
    for event in sorted_events:
        if (event.repo, event.issue_number) not in issue_key_set:
            continue
        # Normalize the label case-insensitively: spec label sets are lower-cased,
        # so a mixed-case event label must be folded before comparison rather than
        # relying on the ingestion layer to have done it.
        normalized_label = event.label.lower() if event.label is not None else None
        if normalized_label is None or normalized_label not in difficulty_label_names:
            continue

        label_key = (event.repo, event.issue_number, normalized_label)
        if event.event_type == "labeled":
            active_since[label_key] = normalize_datetime(event.occurred_at)
        elif event.event_type == "unlabeled":
            active_since.pop(label_key, None)

    # An issue qualifies when it still carries a difficulty label that was
    # applied within the window (on or after the cutoff).
    labeled: set[tuple[str, int]] = {
        (repo, number)
        for (repo, number, _label), applied_at in active_since.items()
        if applied_at is not None and cutoff is not None and applied_at >= cutoff
    }

    # Fallback: include issues created after the cutoff whose current labels
    # match a difficulty spec but lack a corresponding timeline event.
    for issue in issues:
        key = (issue.repo, issue.number)
        if key in labeled:
            continue
        if issue.created_at >= cutoff:
            for spec in difficulty_specs:
                if spec.matches(set(issue.labels)):
                    labeled.add(key)
                    break

    return labeled


def issues_unlabeled_created_since(
    issues: list[IssueRecord],
    cutoff: datetime,
    difficulty_specs: tuple[LabelSpec, ...],
) -> set[tuple[str, int]]:
    """Return (repo, number) pairs for issues created since cutoff lacking a difficulty label.

    These form the "Unknown" bucket.  Unlike labeled issues, an untriaged
    issue has no ``labeled`` event to anchor to, so the bucket is anchored to
    issue *creation* date instead: it captures newly opened issues that have
    not yet been assigned a difficulty.  This keeps the Unknown category
    meaningful (and distinct from the labeled buckets, which are anchored to
    label-application date) rather than collapsing it to zero.
    """
    unknown: set[tuple[str, int]] = set()
    for issue in issues:
        if issue.created_at < cutoff:
            continue
        if any(spec.matches(set(issue.labels)) for spec in difficulty_specs):
            continue
        unknown.add((issue.repo, issue.number))

    return unknown