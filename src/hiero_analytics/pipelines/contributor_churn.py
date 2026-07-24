"""Runner: contributor churn and progression analysis for a single repository."""

import logging

import pandas as pd

from hiero_analytics.analysis.contributor_churn import compute_progression_stats, compute_transition_metrics
from hiero_analytics.analysis.difficulty_analysis import assign_difficulty
from hiero_analytics.analysis.prs import prs_to_dataframe
from hiero_analytics.config.github import GITHUB_TOKEN
from hiero_analytics.config.paths import ORG, REPO
from hiero_analytics.data_sources.github_ingest import fetch_repo_merged_pr_difficulty_graphql
from hiero_analytics.domain.labels import DIFFICULTY_ORDER
from hiero_analytics.domain.repos import bare_repo
from hiero_analytics.pipelines._shared import repo_context
from hiero_analytics.plotting.bars import plot_bar
from hiero_analytics.plotting.lines import plot_line

logger = logging.getLogger(__name__)


def main(org: str = ORG, repo: str = REPO) -> None:
    """Fetch PR data, compute contributor churn metrics, and write charts to disk."""
    if not GITHUB_TOKEN:
        raise OSError("GITHUB_TOKEN not set. Real data is required for churn analysis.")

    short_repo = bare_repo(repo)
    client, repo_data_dir, repo_charts_dir = repo_context(org, repo)
    logger.info("Fetching PR data for %s/%s...", org, repo)
    prs = fetch_repo_merged_pr_difficulty_graphql(client, owner=org, repo=repo, use_cache=True)

    df = prs_to_dataframe(prs)
    if df.empty:
        raise ValueError(f"No PR data found for {org}/{repo}. Cannot perform churn analysis.")

    df["level"] = df["issue_labels"].apply(assign_difficulty)

    df = df.dropna(subset=["author", "pr_merged_at"]).sort_values(["author", "pr_merged_at"])

    # Core analysis logic moved to hiero_analytics.analysis.contributor_churn
    progression = compute_progression_stats(df)

    # Filter to GFI starters
    gfi_starters = progression[progression["start_level"] == "Good First Issue"].copy()
    total_gfi = len(gfi_starters)

    if total_gfi == 0:
        logger.info("No GFI starters found.")
        return

    # Stats Summary
    reached_beginner = len(gfi_starters[gfi_starters["max_level"].isin(["Beginner", "Intermediate", "Advanced"])])
    reached_intermediate = len(gfi_starters[gfi_starters["max_level"].isin(["Intermediate", "Advanced"])])
    reached_advanced = len(gfi_starters[gfi_starters["max_level"] == "Advanced"])

    funnel_df = pd.DataFrame(
        [
            {"stage": "GFI Starters", "count": total_gfi},
            {"stage": "Progressed to Beginner+", "count": reached_beginner},
            {"stage": "Progressed to Intermediate+", "count": reached_intermediate},
            {"stage": "Progressed to Advanced", "count": reached_advanced},
        ]
    )

    logger.info("--- Contributor Churn Analysis ---")
    for _, row in funnel_df.iterrows():
        logger.info("%s: %s (%.1f%%)", row["stage"], row["count"], row["count"] / total_gfi * 100)

    # Transition Metrics (only for GFI starters to match funnel)
    logger.info("--- Level Transition Metrics (GFI Starters only) ---")
    gfi_author_list = gfi_starters.index.tolist()
    gfi_starter_prs = df[df["author"].isin(gfi_author_list)]
    transitions = compute_transition_metrics(gfi_starter_prs)
    if not transitions.empty:
        logger.info("%s", transitions.to_string(index=False))
    else:
        logger.info("No transitions detected.")

    # Save progression data for verification
    csv_path = repo_data_dir / "contributor_progression.csv"
    gfi_starters.to_csv(csv_path)
    logger.info("Detailed progression data for GFI starters saved to: %s", csv_path)

    # Visualizations using project utilities
    plot_bar(
        df=funnel_df,
        x_col="stage",
        y_col="count",
        title=f"{short_repo}: Contributor Progression Funnel",
        output_path=repo_charts_dir / "contributor_churn_funnel.png",
    )

    # Retention Chart - extended range as requested
    max_prs = int(gfi_starters["pr_count"].max()) if not gfi_starters.empty else 10
    retention_df = pd.DataFrame(
        [
            {"min_prs": i, "contributors": len(gfi_starters[gfi_starters["pr_count"] >= i])}
            for i in range(1, max_prs + 1)
        ]
    )

    plot_line(
        df=retention_df,
        x_col="min_prs",
        y_col="contributors",
        title=f"{short_repo}: Contributor Retention by PR Count",
        output_path=repo_charts_dir / "contributor_retention.png",
    )

    # New Visualization: Level Transitions
    if not transitions.empty:
        trans_plot_df = transitions.copy()
        trans_plot_df["transition"] = trans_plot_df["from"] + " -> " + trans_plot_df["to"]
        plot_bar(
            df=trans_plot_df,
            x_col="transition",
            y_col="count",
            title=f"{short_repo}: GFI Starter Level Transitions",
            output_path=repo_charts_dir / "contributor_transitions.png",
        )

    # New Visualization: Average Tenure by Max Level reached
    tenure_by_level = gfi_starters.groupby("max_level")["tenure_days"].mean().reset_index()
    tenure_by_level = tenure_by_level.rename(columns={"tenure_days": "avg_tenure_days"})
    tenure_by_level["max_level"] = pd.Categorical(
        tenure_by_level["max_level"], categories=DIFFICULTY_ORDER, ordered=True
    )
    tenure_by_level = tenure_by_level.sort_values("max_level")

    plot_bar(
        df=tenure_by_level,
        x_col="max_level",
        y_col="avg_tenure_days",
        title=f"{short_repo}: Avg Tenure (Days) by Max Level Reached",
        output_path=repo_charts_dir / "avg_tenure_by_level.png",
    )
