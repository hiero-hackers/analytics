"""
Run onboarding analytics pipeline for a GitHub org.

Produces analytics for:
- Good First Issues (GFI)
- Good First Issue Candidates (GFIC)
- Onboarding pipeline (GFIC → GFI)
"""

from __future__ import annotations

import pandas as pd

from hiero_analytics.analysis.dataframe_utils import (
    count_by,
    filter_by_labels,
    issues_to_dataframe,
)
from hiero_analytics.analysis.onboarding_pipeline import (
    build_gfi_pipeline,
    build_onboarding_repo_pipeline,
)
from hiero_analytics.config.charts import ONBOARDING_COLORS, STATE_COLORS
from hiero_analytics.config.paths import ORG, ensure_org_dirs
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import fetch_org_issues_graphql
from hiero_analytics.domain.labels import (
    GOOD_FIRST_ISSUE,
    GOOD_FIRST_ISSUE_CANDIDATE,
)
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.plotting.bars import plot_stacked_bar
from hiero_analytics.plotting.lines import plot_multiline

STACK_COLS = ["gfic", "gfi"]
STACK_LABELS = [
    GOOD_FIRST_ISSUE_CANDIDATE.name,
    GOOD_FIRST_ISSUE.name,
]


def add_total_state(df: pd.DataFrame) -> pd.DataFrame:
    """Append total counts to a state dataframe."""
    total = df.groupby("year", as_index=False)["count"].sum()
    total["state"] = "total"
    return pd.concat([df, total], ignore_index=True)


def main() -> None:
    """Execute onboarding analytics pipeline."""
    org_data_dir, org_charts_dir = ensure_org_dirs(ORG)

    print(f"Running onboarding analytics for org: {ORG}")

    client = GitHubClient()
    issues = fetch_org_issues_graphql(client, org=ORG)

    print(f"Fetched {len(issues)} issues")

    df = issues_to_dataframe(issues)

    # Clean repo names
    df["repo"] = df["repo"].str.split("/").str[-1]

    # --------------------------------------------------
    # Filter onboarding label groups
    # --------------------------------------------------

    gfi_df = filter_by_labels(df, GOOD_FIRST_ISSUE.labels)
    gfic_df = filter_by_labels(df, GOOD_FIRST_ISSUE_CANDIDATE.labels)

    # --------------------------------------------------
    # Aggregations
    # --------------------------------------------------

    gfi_yearly = count_by(gfi_df, "year")
    gfi_yearly_state = count_by(gfi_df, "year", "state")
    gfi_yearly_state_total = add_total_state(gfi_yearly_state)

    gfi_total_by_repo = count_by(gfi_df, "repo")
    gfic_yearly = count_by(gfic_df, "year")
    gfic_total_by_repo = count_by(gfic_df, "repo")

    # --------------------------------------------------
    # Build pipeline datasets
    # --------------------------------------------------

    pipeline = build_gfi_pipeline(gfi_yearly, gfic_yearly)

    repo_pipeline = build_onboarding_repo_pipeline(
        gfi_total_by_repo,
        gfic_total_by_repo,
    )

    # Sort repos for readability
    if not repo_pipeline.empty:
        repo_pipeline["total"] = repo_pipeline[STACK_COLS].sum(axis=1)
        repo_pipeline = repo_pipeline.sort_values("total", ascending=False)

    # --------------------------------------------------
    # Save datasets
    # --------------------------------------------------

    save_dataframe(gfi_yearly, org_data_dir / "gfi_yearly.csv")
    save_dataframe(gfi_total_by_repo, org_data_dir / "gfi_total_by_repo.csv")
    save_dataframe(gfic_yearly, org_data_dir / "gfic_yearly.csv")
    save_dataframe(pipeline, org_data_dir / "gfi_pipeline.csv")
    save_dataframe(repo_pipeline, org_data_dir / "onboarding_repo_pipeline.csv")

    print("Saved analytics tables")

    # --------------------------------------------------
    # Charts
    # --------------------------------------------------

    if not pipeline.empty:
        plot_stacked_bar(
            pipeline,
            x_col="year",
            stack_cols=STACK_COLS,
            labels=STACK_LABELS,
            colors=ONBOARDING_COLORS,
            title="Onboarding Migration Pipeline (Candidate → Approved) Yearly",
            output_path=org_charts_dir / "gfi_pipeline.png",
        )

    if not repo_pipeline.empty:
        plot_stacked_bar(
            repo_pipeline,
            x_col="repo",
            stack_cols=STACK_COLS,
            labels=STACK_LABELS,
            colors=ONBOARDING_COLORS,
            title="Total Onboarding Issue Pool by Repository",
            output_path=org_charts_dir / "total_gfi_gfic_by_repo.png",
            rotate_x=45,
        )

    if not gfi_yearly_state_total.empty:
        plot_multiline(
            gfi_yearly_state_total,
            x_col="year",
            y_col="count",
            group_col="state",
            colors=STATE_COLORS,
            title="Good First Issues by State per Year",
            output_path=org_charts_dir / "gfi_yearly_state_line.png",
        )

    print("Charts generated")
    print("Analytics pipeline completed")


if __name__ == "__main__":
    main()