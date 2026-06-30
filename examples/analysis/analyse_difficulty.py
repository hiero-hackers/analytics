from __future__ import annotations

from hiero_analytics.analysis.dataframe_utils import issues_to_dataframe
from hiero_analytics.analysis.difficulty_analysis import build_difficulty_dataframe
from hiero_analytics.config.paths import ensure_output_dirs
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import fetch_repo_issues_graphql
from hiero_analytics.domain.labels import DIFFICULTY_LEVELS

OWNER = "hiero-ledger"
REPO = "hiero-sdk-python"


def main() -> None:

    ensure_output_dirs()

    client = GitHubClient()

    issues = fetch_repo_issues_graphql(
        client,
        owner=OWNER,
        repo=REPO,
    )

    print(f"\nDifficulty analysis for {OWNER}/{REPO}")
    print("Total issues:", len(issues))

    # --------------------------------------------------
    # Convert to DataFrame
    # --------------------------------------------------

    df = issues_to_dataframe(issues)

    # --------------------------------------------------
    # Difficulty analytics
    # --------------------------------------------------

    open_df = build_difficulty_dataframe(
        df,
        DIFFICULTY_LEVELS,
        state="open",
    )

    closed_df = build_difficulty_dataframe(
        df,
        DIFFICULTY_LEVELS,
        state="closed",
    )

    total_df = build_difficulty_dataframe(
        df,
        DIFFICULTY_LEVELS,
    )

    # --------------------------------------------------
    # Merge results
    # --------------------------------------------------

    merged = (
        total_df.rename(columns={"count": "count_total"})
        .merge(
            open_df.rename(columns={"count": "count_open"}),
            on="difficulty",
        )
        .merge(
            closed_df.rename(columns={"count": "count_closed"}),
            on="difficulty",
        )
    )

    # --------------------------------------------------
    # Print results
    # --------------------------------------------------

    print("\nDifficulty distribution\n")

    for _, row in merged.iterrows():
        print(
            f"{row['difficulty']:12} | "
            f"{row['count_open']} open | "
            f"{row['count_closed']} closed | "
            f"{row['count_total']} total"
        )


if __name__ == "__main__":
    main()