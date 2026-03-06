"""
Run onboarding analytics pipeline for a GitHub org.

Produces analytics for:
- Good First Issues (GFI)
- Good First Issue Candidates (GFIC)
- Onboarding pipeline (GFIC → GFI)
"""

from __future__ import annotations

from hiero_analytics.config.paths import (
    ensure_output_dirs,
    DATA_DIR,
    CHARTS_DIR,
    ORG,
)

from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_graphql import fetch_org_issues_graphql

from hiero_analytics.identity.issue_normalizer import normalize_issues
from hiero_analytics.transform.dataframe import issues_to_dataframe
from hiero_analytics.transform.save import save_dataframe

from hiero_analytics.domain.labels import (
    GOOD_FIRST_ISSUE,
    GOOD_FIRST_ISSUE_CANDIDATE,
)

from hiero_analytics.metrics.label_metrics import label_metrics
from hiero_analytics.metrics.onboarding import build_gfi_pipeline
from hiero_analytics.metrics.onboarding import build_onboarding_repo_pipeline
from hiero_analytics.metrics.plotting.domain.pipeline import plot_onboarding_by_repo
from hiero_analytics.metrics.plotting.domain.pipeline import (
    plot_label_yearly_trend,
    plot_label_total_by_repo,
    plot_label_yearly_distribution,
    plot_label_pipeline,
)


def main() -> None:
    """
    Execute the onboarding analytics pipeline.
    """

    ensure_output_dirs()

    print(f"Running onboarding analytics for org: {ORG}")

    # --------------------------------------------------
    # Fetch issues
    # --------------------------------------------------

    client = GitHubClient()

    raw = fetch_org_issues_graphql(
        client,
        org=ORG,
    )

    print(f"Fetched {len(raw)} raw issues")

    # --------------------------------------------------
    # Normalize issues
    # --------------------------------------------------

    issues = normalize_issues(raw)

    print(f"Normalized {len(issues)} issues")

    # --------------------------------------------------
    # Transform → DataFrame
    # --------------------------------------------------

    df = issues_to_dataframe(issues)

    print("Converted issues to dataframe")

    # --------------------------------------------------
    # Compute metrics
    # --------------------------------------------------

    gfi_metrics = label_metrics(df, GOOD_FIRST_ISSUE)
    gfic_metrics = label_metrics(df, GOOD_FIRST_ISSUE_CANDIDATE)

    gfi_yearly = gfi_metrics["yearly"]
    gfi_yearly_by_repo = gfi_metrics["yearly_by_repo"]
    
    gfi_total_by_repo = gfi_metrics["total_by_repo"]
    gfic_total_by_repo = gfic_metrics["total_by_repo"]

    gfic_yearly = gfic_metrics["yearly"]
    print("Computed label metrics")

    # --------------------------------------------------
    # Build onboarding pipeline dataset
    # --------------------------------------------------

    pipeline = build_gfi_pipeline(
        gfi_yearly,
        gfic_yearly,
    )

    repo_pipeline = build_onboarding_repo_pipeline(
        gfi_total_by_repo,
        gfic_total_by_repo,
    )

    # --------------------------------------------------
    # Save analytics tables
    # --------------------------------------------------

    save_dataframe(gfi_yearly, DATA_DIR / "gfi_yearly.csv")
    save_dataframe(gfi_yearly_by_repo, DATA_DIR / "gfi_yearly_by_repo.csv")
    save_dataframe(gfi_total_by_repo, DATA_DIR / "gfi_total_by_repo.csv")
    save_dataframe(gfic_yearly, DATA_DIR / "gfic_yearly.csv")
    save_dataframe(pipeline, DATA_DIR / "gfi_pipeline.csv")
    save_dataframe(repo_pipeline, DATA_DIR / "onboarding_repo_pipeline.csv")

    print("Saved analytics tables")

    # --------------------------------------------------
    # Charts
    # --------------------------------------------------

    plot_label_yearly_trend(
        gfi_yearly,
        title=f"{GOOD_FIRST_ISSUE.name} per Year",
        output_path=CHARTS_DIR / "gfi_yearly_line.png",
    )

    plot_label_yearly_distribution(
        gfi_yearly,
        title=f"{GOOD_FIRST_ISSUE.name} per Year",
        output_path=CHARTS_DIR / "gfi_yearly_bar.png",
    )

    plot_label_total_by_repo(
        gfi_total_by_repo,
        title=f"{GOOD_FIRST_ISSUE.name} by Repository",
        output_path=CHARTS_DIR / "gfi_total_by_repo.png",
    )

    plot_label_pipeline(
        pipeline,
        stack_cols=["gfic", "gfi"],
        labels=[
            GOOD_FIRST_ISSUE_CANDIDATE.name,
            GOOD_FIRST_ISSUE.name,
        ],
        title="Onboarding Pipeline (GFIC → GFI)",
        output_path=CHARTS_DIR / "gfi_pipeline.png",
    )

    plot_onboarding_by_repo(
        repo_pipeline,
        title="Onboarding Pipeline by Repository",
        output_path=CHARTS_DIR / "onboarding_pipeline_by_repo.png",
    )
    
    print("Charts generated")
    print("Analytics pipeline completed")


if __name__ == "__main__":
    main()