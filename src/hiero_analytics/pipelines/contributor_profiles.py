"""
Plot average contribution mix by contributor type.

Output:
- avg_contribution_mix_by_type.csv
- avg_contribution_mix.png
"""

from __future__ import annotations

import logging

import pandas as pd

from hiero_analytics.analysis.difficulty_analysis import assign_difficulty
from hiero_analytics.analysis.prs import prs_to_dataframe
from hiero_analytics.config.paths import ORG, REPO
from hiero_analytics.data_sources.github_ingest import (
    fetch_repo_merged_pr_difficulty_graphql,
)
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.pipelines._shared import repo_context
from hiero_analytics.plotting.bars import plot_bar, plot_stacked_bar

PLOT_DIFFICULTY_ORDER = [
    "Good First Issue",
    "Beginner",
    "Intermediate",
    "Advanced",
]


# Helpers
# =========================================================


logger = logging.getLogger(__name__)


def classify_contributor(row):
    """Classify a contributor row into a difficulty tier based on their highest PR difficulty."""
    if row.get("Advanced", 0) > 0:
        return "Advanced contributor"
    if row.get("Intermediate", 0) > 0:
        return "Intermediate contributor"
    if row.get("Beginner", 0) > 0:
        return "Beginner contributor"
    return "GFI contributor"


def build_max_difficulty_distribution(pr_df: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame counting contributors by the highest difficulty PR they merged."""
    df = pr_df.copy()
    df["difficulty"] = df["issue_labels"].apply(assign_difficulty)

    # count per contributor per difficulty
    per_user = df.groupby(["author", "difficulty"]).size().unstack(fill_value=0)
    # define difficulty order (low → high)
    order = PLOT_DIFFICULTY_ORDER

    def get_max(row):
        for level in reversed(order):
            if row.get(level, 0) > 0:
                return level
        return "Unknown"

    per_user["max_difficulty"] = per_user.apply(get_max, axis=1)
    # count contributors by max difficulty
    result = per_user["max_difficulty"].value_counts().rename_axis("difficulty").reset_index(name="count")

    result = result[result["difficulty"].isin(order)]
    # enforce correct order
    result["difficulty"] = pd.Categorical(
        result["difficulty"],
        categories=order,
        ordered=True,
    )

    return result.sort_values("difficulty")


# =========================================================
# Core: average contribution mix
# =========================================================


def build_avg_contribution_mix(pr_df: pd.DataFrame) -> pd.DataFrame:
    """Return mean PRs-per-difficulty for each contributor type."""
    # assign difficulty per PR
    df = pr_df.copy()
    df["difficulty"] = df["issue_labels"].apply(assign_difficulty)

    # count per contributor per difficulty
    per_user = df.groupby(["author", "difficulty"]).size().unstack(fill_value=0)

    per_user["total"] = per_user.sum(axis=1)

    # classify contributors
    per_user["contributor_type"] = per_user.apply(classify_contributor, axis=1)

    # average per contributor type
    return per_user.groupby("contributor_type").mean(numeric_only=True).reset_index()


# =========================================================
# Plot
# =========================================================
def plot_max_difficulty(df: pd.DataFrame, output_path, repo: str):
    """Render a bar chart of contributors grouped by maximum difficulty reached."""
    plot_bar(
        df=df,
        x_col="difficulty",
        y_col="count",
        title=f"{repo}: Max Difficulty Reached by Contributors",
        output_path=output_path,
        rotate_x=30,
    )


def plot_avg_mix(df: pd.DataFrame, output_path, repo: str):
    """Render a stacked bar chart showing the average difficulty mix per contributor type."""
    if "total" in df.columns:
        df = df.drop(columns=["total"])

    CONTRIBUTOR_ORDER = [
        "GFI contributor",
        "Beginner contributor",
        "Intermediate contributor",
        "Advanced contributor",
    ]

    df["contributor_type"] = pd.Categorical(
        df["contributor_type"],
        categories=CONTRIBUTOR_ORDER,
        ordered=True,
    )

    df = df.sort_values("contributor_type")

    # enforce stack order
    stack_cols = [
        "Good First Issue",
        "Beginner",
        "Intermediate",
        "Advanced",
    ]
    stack_cols = [c for c in stack_cols if c in df.columns]

    plot_stacked_bar(
        df=df,
        x_col="contributor_type",
        stack_cols=stack_cols,
        labels=stack_cols,
        title=f"{repo}: Average Contribution",
        output_path=output_path,
        rotate_x=30,
    )


# =========================================================
# Main
# =========================================================


def main(org: str = ORG, repo: str = REPO):
    """Fetch PR difficulty data and generate contributor profile charts for a repository."""
    client, repo_data_dir, repo_charts_dir = repo_context(org, repo)

    prs = fetch_repo_merged_pr_difficulty_graphql(
        client,
        owner=org,
        repo=repo,
    )

    pr_df = prs_to_dataframe(prs)

    logger.info("Fetched %d PRs", len(pr_df))

    # build dataset
    avg_mix = build_avg_contribution_mix(pr_df)

    # save
    save_dataframe(
        avg_mix,
        repo_data_dir / "avg_contribution_mix_by_type.csv",
    )

    # plot
    plot_avg_mix(
        avg_mix,
        repo_charts_dir / "avg_contribution_mix.png",
        repo,
    )

    plot_max_difficulty(
        build_max_difficulty_distribution(pr_df),
        repo_charts_dir / "max_difficulty_distribution.png",
        repo,
    )

    logger.info("Done.")
