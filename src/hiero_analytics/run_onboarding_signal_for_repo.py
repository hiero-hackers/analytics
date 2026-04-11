import pathlib
import numpy as np
from matplotlib.axes import Axes

from hiero_analytics.config.charts import PRIMARY_PALETTE
from hiero_analytics.config.logging import setup_logging
from hiero_analytics.config.paths import ORG

from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import (
    fetch_repo_issues_graphql,
    fetch_repo_merged_pr_difficulty_graphql,
)

from hiero_analytics.analysis.dataframe_utils import (
    issues_to_dataframe,
    filter_by_labels,
)
from hiero_analytics.analysis.timeseries import cumulative_timeseries
from hiero_analytics.analysis.prs import (
    prs_to_dataframe,
    filter_gfi_prs,
)

from hiero_analytics.domain.labels import ALL_ONBOARDING, DIFFICULTY_LEVELS
import matplotlib.pyplot as plt
import pandas as pd

from hiero_analytics.plotting.base import create_figure, finalize_chart
from hiero_analytics.plotting.primitives import annotate_endpoint_badge
from hiero_analytics.plotting.scatter import plot_scatter_with_regression

setup_logging()

ORG_NAME = ORG
REPO = "hiero-sdk-python"
short_repo = REPO.split("/")[-1]

from hiero_analytics.config.paths import ensure_repo_dirs


def plot_issue_vs_contributors(
    issues_ts: pd.DataFrame,
    contrib_ts: pd.DataFrame,
    output_path: pathlib.Path,
    *,
    issue_date_col: str = "created_at",
    contrib_date_col: str = "pr_merged_at",
    issue_label: str = "Issues",
    contrib_label: str = "Contributors",
    title: str,
) -> None:

    issues = issues_ts.sort_values(issue_date_col).rename(columns={issue_date_col: "date", "count": "issue_count"})

    contrib = contrib_ts.sort_values(contrib_date_col).rename(
        columns={contrib_date_col: "date", "count": "contrib_count"}
    )

    df = pd.merge_asof(
        issues,
        contrib,
        on="date",
        direction="backward",
    ).dropna()

    if df.empty:
        raise ValueError("No overlapping data")

    plot_scatter_with_regression(
        df,
        x_col="issue_count",
        y_col="contrib_count",
        title=title,
        xlabel=f"Cumulative {issue_label}",
        ylabel=f"Cumulative {contrib_label}",
        output_path=output_path,
    )


def run():
    client = GitHubClient()
    repo_data_dir, repo_charts_dir = ensure_repo_dirs(f"{ORG_NAME}/{REPO}")

    # ----------------------------------------
    # GFI supply (issues)
    # ----------------------------------------
    issues = fetch_repo_issues_graphql(
        client,
        owner=ORG_NAME,
        repo=REPO,
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
        owner=ORG_NAME,
        repo=REPO,
    )

    pr_df = prs_to_dataframe(prs)

    # only PRs that closed onboarding issues
    gfi_pr_df = filter_gfi_prs(pr_df)

    # unique contributors (first PR only)
    contrib_df = gfi_pr_df.dropna(subset=["author"]).sort_values("pr_merged_at").drop_duplicates("author")

    contrib_ts = cumulative_timeseries(contrib_df, "pr_merged_at")

    def plot_onboarding_signal(
        gfi_ts: pd.DataFrame,
        contrib_ts: pd.DataFrame,
        output_path: pathlib.Path,
    ) -> None:
        """
        Plot onboarding signal:
        - GFI cumulative (left axis)
        - unique contributors (right axis)
        """

        if gfi_ts.empty or contrib_ts.empty:
            raise ValueError("Input time series cannot be empty")

        fig, ax1 = create_figure()

        # -------------------------
        # GFI (left axis)
        # -------------------------
        gfi = gfi_ts.sort_values("created_at")

        ax1.plot(
            gfi["created_at"],
            gfi["count"],
            color=PRIMARY_PALETTE[2],
            linewidth=2.6,
            zorder=3,
        )

        annotate_endpoint_badge(
            ax1,
            x=gfi["created_at"].iloc[-1],
            y=gfi["count"].iloc[-1],
            text=f"GFI {int(gfi['count'].iloc[-1])}",
            color=PRIMARY_PALETTE[2],
            y_offset=-6,
        )

        ax1.set_ylabel("Good First Issues")

        # -------------------------
        # Contributors (right axis)
        # -------------------------
        ax2: Axes = ax1.twinx()

        contrib = contrib_ts.sort_values("pr_merged_at")

        ax2.plot(
            contrib["pr_merged_at"],
            contrib["count"],
            color=PRIMARY_PALETTE[4],
            linewidth=2.6,
            zorder=3,
        )

        annotate_endpoint_badge(
            ax2,
            x=contrib["pr_merged_at"].iloc[-1],
            y=contrib["count"].iloc[-1],
            text=f"Contrib {int(contrib['count'].iloc[-1])}",
            color=PRIMARY_PALETTE[4],
            y_offset=6,
        )

        ax2.set_ylabel("Cumulative Good First Issue Contributors With a Merged PR")

        # -------------------------
        # Finalize
        # -------------------------
        finalize_chart(
            fig=fig,
            ax=ax1,
            title=f"{short_repo}: Cumulative Onboarding Issues (GFIs & Candidates) vs Cumulative Merged PR Contributors",
            xlabel="Date",
            ylabel="Cumulative Good First Issues",
            output_path=output_path,
            legend=False,
            grid_axis="y",
        )

    # ----------------------------------------
    # Plot
    # ----------------------------------------
    plot_onboarding_signal(
        gfi_ts,
        contrib_ts,
        pathlib.Path(repo_charts_dir) / "onboarding_signal.png",
    )
    # ----------------------------------------
    # Per-difficulty plots
    # ----------------------------------------
    for spec in DIFFICULTY_LEVELS:
        safe_name = spec.name.replace(" ", "_").lower()

        # -------------------------
        # Filter issues by difficulty
        # -------------------------
        issues_subset = issues_df[issues_df["labels"].apply(lambda xs: spec.matches(set(xs or [])))]
        issues_ts_subset = cumulative_timeseries(issues_subset, "created_at")

        # -------------------------
        # Filter PRs by difficulty (via issue_labels)
        # -------------------------
        prs_subset = pr_df[pr_df["issue_labels"].apply(lambda xs: spec.matches(set(xs or [])))]

        # -------------------------
        # Unique contributors per difficulty
        # -------------------------
        contrib_df_subset = prs_subset.dropna(subset=["author"]).sort_values("pr_merged_at").drop_duplicates("author")

        contrib_ts_subset = cumulative_timeseries(
            contrib_df_subset,
            "pr_merged_at",
        )

        if issues_ts_subset.empty or contrib_ts_subset.empty:
            print(f"Skipping {spec.name}: no data")
            continue

        # -------------------------
        # Plot
        # -------------------------
        plot_issue_vs_contributors(
            issues_ts_subset,
            contrib_ts_subset,
            output_path=repo_charts_dir / f"{safe_name}.png",
            issue_label=f"{spec.name} Issues",
            contrib_label=f"{spec.name} Contributors",
            title=f"{short_repo}: {spec.name} Onboarding Efficiency",
        )


if __name__ == "__main__":
    run()
