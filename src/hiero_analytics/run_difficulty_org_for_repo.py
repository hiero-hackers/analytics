"""
Run difficulty analytics for an org.

Produces:
- Difficulty distribution pie charts
- Difficulty distribution by repository (stacked bar)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hiero_analytics.analysis.dataframe_utils import issues_to_dataframe
from hiero_analytics.config.charts import DIFFICULTY_COLORS
from hiero_analytics.config.paths import ORG, ensure_org_dirs
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import fetch_org_issues_graphql
from hiero_analytics.domain.labels import (
    DIFFICULTY_LEVELS,
    DIFFICULTY_ORDER,
    UNKNOWN_DIFFICULTY,
)
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.plotting.bars import plot_stacked_bar
from hiero_analytics.plotting.pie import plot_pie


def assign_difficulty(labels, specs):
    """Return the first matching difficulty label for an issue."""
    for spec in specs:
        if spec.matches(labels):
            return spec.name
    return UNKNOWN_DIFFICULTY


def main() -> None:
    """Run the difficulty analytics pipeline for the configured organization."""
    org_data_dir, org_charts_dir = ensure_org_dirs(ORG)

    print(f"Running difficulty analytics for org: {ORG}")

    client = GitHubClient()
    issues = fetch_org_issues_graphql(client, org=ORG)

    print(f"Fetched {len(issues)} issues")

    df = issues_to_dataframe(issues)

    cutoff = datetime.now(UTC) - timedelta(days=30)

    df = df[(df["state"] == "open") & (df["created_at"] >= cutoff)].copy()

    # Remove org prefix from repo name
    df["repo"] = df["repo"].str.split("/").str[-1]

    # Only analyze OPEN issues
    df = df[df["state"] == "open"].copy()

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
            "Open Issues (Created Last 30 Days) by Difficulty Distribution (Including Unknown)",
            "difficulty_distribution_with_unknown_30_days.png",
        ),
        (
            difficulty_counts[difficulty_counts["difficulty"] != UNKNOWN_DIFFICULTY],
            "Open Issues (Created Last 30 Days) by Difficulty Distribution (Excluding Unknown)",
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
        title="Open Issues (Created Last 30 Days) by Difficulty Distribution in a Repository",
        output_path=org_charts_dir / "difficulty_by_repo_30_days.png",
        colors=DIFFICULTY_COLORS,
        rotate_x=45,
    )

    print("Difficulty analytics complete")


if __name__ == "__main__":
    main()
