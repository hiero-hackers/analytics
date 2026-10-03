"""Runner script for onboarding signal analysis: GFI supply vs contributor demand over time."""

import logging

import pandas as pd

from hiero_analytics.analysis.dataframe_utils import (
    filter_by_labels,
    issues_to_dataframe,
)
from hiero_analytics.analysis.prs import (
    filter_gfi_prs,
    prs_to_dataframe,
)
from hiero_analytics.analysis.timeseries import cumulative_timeseries
from hiero_analytics.config.paths import ORG, REPO
from hiero_analytics.data_sources.github_ingest import (
    fetch_repo_issues_graphql,
    fetch_repo_merged_pr_difficulty_graphql,
)
from hiero_analytics.domain.labels import ALL_ONBOARDING, DIFFICULTY_LEVELS
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.pipelines._shared import repo_context

logger = logging.getLogger(__name__)


def issue_vs_contributor_table(
    issues_ts: pd.DataFrame,
    contrib_ts: pd.DataFrame,
    *,
    issue_date_col: str = "created_at",
    contrib_date_col: str = "pr_merged_at",
) -> pd.DataFrame:
    """Pair cumulative issues with cumulative contributors as of each issue date.

    Each issue-count point is matched to the latest contributor count on or
    before it (``merge_asof``). Returns ``date``, ``issue_count`` and
    ``contrib_count``; the frame is empty when the series do not overlap.
    """
    issues = issues_ts.sort_values(issue_date_col).rename(columns={issue_date_col: "date", "count": "issue_count"})

    contrib = contrib_ts.sort_values(contrib_date_col).rename(
        columns={contrib_date_col: "date", "count": "contrib_count"}
    )

    return pd.merge_asof(
        issues,
        contrib,
        on="date",
        direction="backward",
    ).dropna()


def onboarding_signal_table(gfi_ts: pd.DataFrame, contrib_ts: pd.DataFrame) -> pd.DataFrame:
    """Stack the two cumulative series long as ``series``, ``date``, ``count`` (no resampling)."""
    gfi = gfi_ts.rename(columns={"created_at": "date"}).assign(series="onboarding_issues")
    contrib = contrib_ts.rename(columns={"pr_merged_at": "date"}).assign(series="contributors")
    return pd.concat([gfi, contrib], ignore_index=True)[["series", "date", "count"]]


def main(org: str = ORG, repo: str = REPO):
    """Fetch onboarding data for the configured repository and write the onboarding tables."""
    client, repo_data_dir = repo_context(org, repo)

    # ----------------------------------------
    # GFI supply (issues)
    # ----------------------------------------
    issues = fetch_repo_issues_graphql(
        client,
        owner=org,
        repo=repo,
        states=["OPEN", "CLOSED"],
    )

    issues_df = issues_to_dataframe(issues)

    gfi_df = filter_by_labels(issues_df, ALL_ONBOARDING.labels)
    gfi_ts = cumulative_timeseries(gfi_df, "created_at")

    # ----------------------------------------
    # Onboarding demand (unique contributors)
    # ----------------------------------------
    prs = fetch_repo_merged_pr_difficulty_graphql(
        client,
        owner=org,
        repo=repo,
    )

    pr_df = prs_to_dataframe(prs)

    # only PRs that closed onboarding issues
    gfi_pr_df = filter_gfi_prs(pr_df)

    # unique contributors (first PR only)
    contrib_df = gfi_pr_df.dropna(subset=["author"]).sort_values("pr_merged_at").drop_duplicates("author")

    contrib_ts = cumulative_timeseries(contrib_df, "pr_merged_at")

    # ----------------------------------------
    # Onboarding signal
    # ----------------------------------------
    if gfi_ts.empty or contrib_ts.empty:
        logger.info("Skipping onboarding signal: no onboarding issues or no contributors")
    else:
        save_dataframe(onboarding_signal_table(gfi_ts, contrib_ts), repo_data_dir / "onboarding_signal.csv")

    # ----------------------------------------
    # Per-difficulty efficiency
    # ----------------------------------------
    if issues_df.empty or pr_df.empty:
        # An empty frame has no labels/issue_labels columns to subset on, and
        # every per-difficulty level would be skipped as no-data anyway.
        logger.info("Skipping per-difficulty efficiency: no issue or PR data")
        return

    efficiency_frames = []
    for spec in DIFFICULTY_LEVELS:
        # -------------------------
        # Filter issues by difficulty
        # -------------------------
        issues_subset = issues_df[issues_df["labels"].apply(lambda xs, _spec=spec: _spec.matches(set(xs or [])))]
        issues_ts_subset = cumulative_timeseries(issues_subset, "created_at")

        # -------------------------
        # Filter PRs by difficulty (via issue_labels)
        # -------------------------
        prs_subset = pr_df[pr_df["issue_labels"].apply(lambda xs, _spec=spec: _spec.matches(set(xs or [])))]

        # -------------------------
        # Unique contributors per difficulty
        # -------------------------
        contrib_df_subset = prs_subset.dropna(subset=["author"]).sort_values("pr_merged_at").drop_duplicates("author")

        contrib_ts_subset = cumulative_timeseries(
            contrib_df_subset,
            "pr_merged_at",
        )

        if issues_ts_subset.empty or contrib_ts_subset.empty:
            logger.info("Skipping %s: no data", spec.name)
            continue

        # -------------------------
        # Pair cumulative issues with cumulative contributors
        # -------------------------
        table = issue_vs_contributor_table(issues_ts_subset, contrib_ts_subset)
        if table.empty:
            logger.info("Skipping %s: no overlapping data", spec.name)
            continue
        efficiency_frames.append(table.assign(difficulty=spec.name))

    if efficiency_frames:
        efficiency = pd.concat(efficiency_frames, ignore_index=True)[
            ["difficulty", "date", "issue_count", "contrib_count"]
        ]
        save_dataframe(efficiency, repo_data_dir / "onboarding_efficiency.csv")
