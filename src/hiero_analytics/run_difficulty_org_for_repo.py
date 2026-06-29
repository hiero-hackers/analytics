"""
Run difficulty analytics for an org.

Produces:
- Difficulty distribution pie charts
- Difficulty distribution by repository (stacked bar)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pandas as pd

from hiero_analytics.analysis.dataframe_utils import issues_to_dataframe
from hiero_analytics.analysis.difficulty_analysis import (
    assign_difficulty,
    issues_labeled_since,
    issues_unlabeled_created_since,
)
from hiero_analytics.config.charts import DIFFICULTY_COLORS
from hiero_analytics.config.logging_config import setup_logging
from hiero_analytics.config.paths import ORG, ensure_org_dirs
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import (
    fetch_org_issue_label_events_graphql,
    fetch_org_issues_graphql,
)
from hiero_analytics.domain.labels import (
    DIFFICULTY_LEVELS,
    DIFFICULTY_ORDER,
    UNKNOWN_DIFFICULTY,
)
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.plotting.bars import plot_stacked_bar
from hiero_analytics.plotting.pie import plot_pie

TIMELINE_MAX_WORKERS = 3


logger = logging.getLogger(__name__)


def main() -> None:
    """Run the difficulty analytics pipeline for the configured organization."""
    org_data_dir, org_charts_dir = ensure_org_dirs(ORG)

    logger.info("Running difficulty analytics for org: %s", ORG)

    client = GitHubClient()
    issues = fetch_org_issues_graphql(client, org=ORG, states=["OPEN"])

    logger.info("Fetched %d issues", len(issues))

    df = issues_to_dataframe(issues)

    cutoff = datetime.now(UTC) - timedelta(days=30)

    # Fetch label add/remove events (GraphQL timelineItems) to determine when
    # difficulty labels were applied. Only LABELED/UNLABELED events are
    # transferred, avoiding the repo-wide REST event firehose.
    timeline_events = fetch_org_issue_label_events_graphql(
        client,
        org=ORG,
        states=["OPEN"],
        max_workers=TIMELINE_MAX_WORKERS,
    )
    logger.info("Fetched %d timeline events", len(timeline_events))

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

    logger.info("Difficulty analytics complete")


if __name__ == "__main__":
    setup_logging()
    main()
