"""
Run difficulty analytics for an org.

Produces:
- Difficulty distribution pie charts
- Difficulty distribution by repository (stacked bar)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from hiero_analytics.analysis.dataframe_utils import issues_to_dataframe
from hiero_analytics.analysis.difficulty_analysis import (
    assign_difficulty,
    issues_labeled_since,
    issues_unlabeled_created_since,
)
from hiero_analytics.config.analysis import DIFFICULTY_RECENT_WINDOWS, TIMELINE_MAX_WORKERS
from hiero_analytics.config.charts import DIFFICULTY_COLORS
from hiero_analytics.config.paths import ORG
from hiero_analytics.data_sources.github_ingest import (
    fetch_org_issue_label_events_graphql,
    fetch_org_issues_graphql,
)
from hiero_analytics.data_sources.models import IssueRecord, IssueTimelineEventRecord
from hiero_analytics.domain.labels import (
    DIFFICULTY_LEVELS,
    DIFFICULTY_ORDER,
)
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.pipelines._shared import org_context
from hiero_analytics.plotting.bars import plot_stacked_bar

logger = logging.getLogger(__name__)


def _run_window(
    df: pd.DataFrame,
    issues: list[IssueRecord],
    timeline_events: list[IssueTimelineEventRecord],
    *,
    window_days: int,
    window_label: str,
    org_data_dir: Path,
    org_charts_dir: Path,
) -> None:
    """Produce the difficulty distribution and per-repo bar outputs for one window."""
    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    distribution_csv = org_data_dir / f"difficulty_distribution_{window_days}_days.csv"
    by_repo_csv = org_data_dir / f"difficulty_by_repo_{window_days}_days.csv"

    # Identify issues that received a difficulty label within the window.
    labeled_issues = issues_labeled_since(
        issues,
        timeline_events,
        cutoff,
        DIFFICULTY_LEVELS,
    )

    # Identify newly created, still-untriaged issues for the Unknown bucket.
    # Anchored to creation date because an unlabeled issue has no labeling
    # event to anchor to.  The two sets are disjoint by construction (an issue
    # either carries an active difficulty label or it does not).
    unknown_issues = issues_unlabeled_created_since(
        issues,
        cutoff,
        DIFFICULTY_LEVELS,
    )

    included_issues = labeled_issues | unknown_issues

    issue_keys = pd.MultiIndex.from_arrays([df["repo"], df["number"]])
    df = df[(df["state"] == "open") & issue_keys.isin(included_issues)].copy()

    if df.empty:
        # A quiet window (no labeling or new issues) is data, not an error;
        # still write the empty CSVs so tabs don't reference missing files,
        # but skip the chart — the plotting layer rejects empty frames.
        logger.info("No issues qualified for the %s window", window_label)
        save_dataframe(pd.DataFrame(columns=["difficulty", "count"]), distribution_csv)
        save_dataframe(pd.DataFrame(columns=["repo", *DIFFICULTY_ORDER]), by_repo_csv)
        return

    # Remove org prefix from repo name
    df["repo"] = df["repo"].str.split("/").str[-1]

    # Assign difficulty
    df["difficulty"] = df["labels"].apply(lambda labels: assign_difficulty(labels, DIFFICULTY_LEVELS))

    # --------------------------------------------------
    # ORG LEVEL DIFFICULTY
    # --------------------------------------------------

    difficulty_counts = df.groupby("difficulty").size().reset_index(name="count")

    save_dataframe(difficulty_counts, distribution_csv)

    # --------------------------------------------------
    # REPO DIFFICULTY STACKED BAR
    # --------------------------------------------------

    pivot = (
        df.groupby(["repo", "difficulty"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=DIFFICULTY_ORDER, fill_value=0)
        .reset_index()
    )

    save_dataframe(pivot, by_repo_csv)

    plot_stacked_bar(
        pivot,
        x_col="repo",
        stack_cols=DIFFICULTY_ORDER,
        labels=DIFFICULTY_ORDER,
        title=f"Labeled or Newly Created Open Issues By Difficulty (in Last {window_label})",
        output_path=org_charts_dir / f"difficulty_by_repo_{window_days}_days.png",
        colors=DIFFICULTY_COLORS,
        rotate_x=45,
    )


def main(org: str = ORG) -> None:
    """Run the difficulty analytics pipeline for the configured organization."""
    client, org_data_dir, org_charts_dir = org_context(org)

    logger.info("Running difficulty analytics for org: %s", org)

    issues = fetch_org_issues_graphql(client, org=org, states=["OPEN"])

    logger.info("Fetched %d issues", len(issues))

    df = issues_to_dataframe(issues)

    # Fetch label add/remove events (GraphQL timelineItems) to determine when
    # difficulty labels were applied. Only LABELED/UNLABELED events are
    # transferred, avoiding the repo-wide REST event firehose.
    timeline_events = fetch_org_issue_label_events_graphql(
        client,
        org=org,
        states=["OPEN"],
        max_workers=TIMELINE_MAX_WORKERS,
    )
    logger.info("Fetched %d timeline events", len(timeline_events))

    # One fetch, one snapshot per configured window (dashboard tabs).
    for window_days, window_label in DIFFICULTY_RECENT_WINDOWS:
        _run_window(
            df,
            issues,
            timeline_events,
            window_days=window_days,
            window_label=window_label,
            org_data_dir=org_data_dir,
            org_charts_dir=org_charts_dir,
        )

    logger.info("Difficulty analytics complete")
