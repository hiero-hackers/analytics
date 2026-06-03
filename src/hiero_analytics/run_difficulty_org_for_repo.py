"""
Run difficulty analytics for an org.

Produces:
- Difficulty distribution pie charts
- Difficulty distribution by repository (stacked bar)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from hiero_analytics.analysis.dataframe_utils import issues_to_dataframe
from hiero_analytics.config.charts import DIFFICULTY_COLORS
from hiero_analytics.config.paths import ORG, ensure_org_dirs
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import (
    fetch_org_issues_graphql,
    fetch_repo_issue_events_for_issues_since,
)
from hiero_analytics.data_sources.models import IssueRecord, IssueTimelineEventRecord
from hiero_analytics.domain.labels import (
    DIFFICULTY_LEVELS,
    DIFFICULTY_ORDER,
    UNKNOWN_DIFFICULTY,
    LabelSpec,
)
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.plotting.bars import plot_stacked_bar
from hiero_analytics.plotting.pie import plot_pie

TIMELINE_MAX_WORKERS = 3


def assign_difficulty(labels, specs):
    """Return the first matching difficulty label for an issue."""
    for spec in specs:
        if spec.matches(labels):
            return spec.name
    return UNKNOWN_DIFFICULTY


_TIMELINE_EVENT_ORDER = {
    "unlabeled": 0,
    "labeled": 1,
    "closed": 2,
    "reopened": 3,
}


def _normalize_datetime(value: datetime | None) -> datetime | None:
    """Return a timezone-aware UTC datetime for stable comparisons."""
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


def _issues_labeled_since(
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
            _normalize_datetime(event.occurred_at),
            _TIMELINE_EVENT_ORDER.get(event.event_type, 99),
        ),
    )

    # Track active difficulty labels per issue: add on "labeled", remove on
    # "unlabeled".  Keyed by (repo, issue_number, label) so that removing
    # one difficulty label does not erase the record of a different one.
    active_labels: set[tuple[str, int, str]] = set()
    for event in sorted_events:
        if (event.repo, event.issue_number) not in issue_key_set:
            continue
        if event.label is None or event.label not in difficulty_label_names:
            continue

        label_key = (event.repo, event.issue_number, event.label)
        if event.event_type == "labeled":
            active_labels.add(label_key)
        elif event.event_type == "unlabeled":
            active_labels.discard(label_key)

    # Derive the set of qualifying issue keys from active labels.
    labeled: set[tuple[str, int]] = {(repo, number) for repo, number, _label in active_labels}

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


def _issues_unlabeled_created_since(
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


def main() -> None:
    """Run the difficulty analytics pipeline for the configured organization."""
    org_data_dir, org_charts_dir = ensure_org_dirs(ORG)

    print(f"Running difficulty analytics for org: {ORG}")

    client = GitHubClient()
    issues = fetch_org_issues_graphql(client, org=ORG, states=["OPEN"])

    print(f"Fetched {len(issues)} issues")

    df = issues_to_dataframe(issues)

    cutoff = datetime.now(UTC) - timedelta(days=30)

    # Fetch timeline events to determine when difficulty labels were applied.
    timeline_events = fetch_repo_issue_events_for_issues_since(
        client,
        issues,
        since=cutoff,
        max_workers=TIMELINE_MAX_WORKERS,
    )
    print(f"Fetched {len(timeline_events)} timeline events")

    # Identify issues that received a difficulty label within the window.
    labeled_issues = _issues_labeled_since(
        issues,
        timeline_events,
        cutoff,
        DIFFICULTY_LEVELS,
    )

    # Identify newly created, still-untriaged issues for the Unknown bucket.
    # Anchored to creation date because an unlabeled issue has no labeling
    # event to anchor to.  The two sets are disjoint by construction (an issue
    # either carries an active difficulty label or it does not).
    unknown_issues = _issues_unlabeled_created_since(
        issues,
        cutoff,
        DIFFICULTY_LEVELS,
    )

    included_issues = labeled_issues | unknown_issues

    issue_keys = pd.MultiIndex.from_arrays([df["repo"], df["number"]])
    df = df[(df["state"] == "open") & issue_keys.isin(included_issues)].copy()

    # Remove org prefix from repo name
    df["repo"] = df["repo"].str.split("/").str[-1]

    # Assign difficulty
    df["difficulty"] = df["labels"].apply(lambda labels: assign_difficulty(labels, DIFFICULTY_LEVELS))

    # --------------------------------------------------
    # ORG LEVEL DIFFICULTY
    # --------------------------------------------------

    difficulty_counts = df.groupby("difficulty").size().reset_index(name="count")

    save_dataframe(
        difficulty_counts,
        org_data_dir / "difficulty_distribution_30_days.csv",
    )

    # Pies

    pie_variants = [
        (
            difficulty_counts,
            "Open Issues by Difficulty Distribution "
            "(Labeled or Newly Created in Last 30 Days, Including Unknown)",
            "difficulty_distribution_with_unknown_30_days.png",
        ),
        (
            difficulty_counts[difficulty_counts["difficulty"] != UNKNOWN_DIFFICULTY],
            "Open Issues by Difficulty Distribution "
            "(Labeled in Last 30 Days, Excluding Unknown)",
            "difficulty_distribution_without_unknown_30_days.png",
        ),
    ]

    for data, title, filename in pie_variants:
        plot_pie(
            data,
            label_col="difficulty",
            value_col="count",
            title=title,
            output_path=org_charts_dir / filename,
            colors=DIFFICULTY_COLORS,
            label_order=DIFFICULTY_ORDER,
            legend_title="Difficulty",
            center_label="Open issues",
        )

    # --------------------------------------------------
    # REPO DIFFICULTY STACKED BAR
    # --------------------------------------------------

    difficulty_cols = [
        UNKNOWN_DIFFICULTY,
        *[spec.name for spec in DIFFICULTY_LEVELS],
    ]

    pivot = (
        df.groupby(["repo", "difficulty"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=difficulty_cols, fill_value=0)
        .reset_index()
    )

    save_dataframe(
        pivot,
        org_data_dir / "difficulty_by_repo_30_days.csv",
    )

    plot_stacked_bar(
        pivot,
        x_col="repo",
        stack_cols=difficulty_cols,
        labels=difficulty_cols,
        title="Labeled or Newly Created Open Issues By Difficulty (in Last 30 Days)",
        output_path=org_charts_dir / "difficulty_by_repo_30_days.png",
        colors=DIFFICULTY_COLORS,
        rotate_x=45,
    )

    print("Difficulty analytics complete")


if __name__ == "__main__":
    main()
