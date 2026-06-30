from __future__ import annotations

from hiero_analytics.analysis.dataframe_utils import (
    count_by,
    filter_by_labels,
    issues_to_dataframe,
)
from hiero_analytics.analysis.onboarding_pipeline import (
    build_gfi_pipeline,
)
from hiero_analytics.config.paths import ORG, REPO, ensure_output_dirs
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import fetch_repo_issues_graphql
from hiero_analytics.domain.labels import (
    GOOD_FIRST_ISSUE,
    GOOD_FIRST_ISSUE_CANDIDATE,
)


def main() -> None:

    ensure_output_dirs()

    client = GitHubClient()
    issues = fetch_repo_issues_graphql(client, owner=ORG, repo=REPO)

    print(f"\nOnboarding analysis for {ORG}/{REPO}")
    print("Total issues:", len(issues))

    df = issues_to_dataframe(issues)

    gfi = filter_by_labels(df, GOOD_FIRST_ISSUE.labels)
    gfic = filter_by_labels(df, GOOD_FIRST_ISSUE_CANDIDATE.labels)

    print("\nLabel counts")
    print("GFI :", len(gfi))
    print("GFIC:", len(gfic))

    gfi_yearly = count_by(gfi, "year")
    gfic_yearly = count_by(gfic, "year")

    pipeline = build_gfi_pipeline(gfi_yearly, gfic_yearly)

    print("\nOnboarding pipeline")
    print(pipeline)


if __name__ == "__main__":
    main()