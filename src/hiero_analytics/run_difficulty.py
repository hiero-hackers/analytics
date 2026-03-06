"""
Run Python SDK difficulty analysis.

Produces:
- Issue difficulty distribution pie
- Closed issue difficulty distribution pie
"""

from __future__ import annotations

import pandas as pd

from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_graphql import fetch_repo_issues_graphql

from hiero_analytics.metrics.plotting.pie import plot_pie
from hiero_analytics.config.paths import ensure_output_dirs, DATA_DIR, CHARTS_DIR
from hiero_analytics.transform.save import save_dataframe


OWNER = "hiero-ledger"
REPO = "hiero-sdk-python"


DIFFICULTY_LABELS = {
    "Good First Issue": {
        "good first issue",
        "skill: good first issue",
    },
    "Beginner": {
        "beginner",
    },
    "Intermediate": {
        "intermediate",
    },
    "Advanced": {
        "advanced",
    },
}


def compute_difficulty_counts(issues):

    results = {
        difficulty: {"total": 0, "closed": 0}
        for difficulty in DIFFICULTY_LABELS
    }

    for issue in issues:

        labels = {l.lower() for l in issue.get("labels", [])}
        state = issue.get("state", "").lower()

        for difficulty, difficulty_labels in DIFFICULTY_LABELS.items():

            if labels & difficulty_labels:

                results[difficulty]["total"] += 1

                if state == "closed":
                    results[difficulty]["closed"] += 1

    return results


def main():

    ensure_output_dirs()

    client = GitHubClient()

    print(f"Running difficulty analysis for {OWNER}/{REPO}")

    issues = fetch_repo_issues_graphql(
        client,
        owner=OWNER,
        repo=REPO,
    )

    print("Total issues:", len(issues))

    results = compute_difficulty_counts(issues)

    print("\nDifficulty counts:\n")

    for difficulty, counts in results.items():

        print(
            f"{difficulty}: "
            f"{counts['total']} total | "
            f"{counts['closed']} closed"
        )

    # ---------------------------------------------------------
    # Build DataFrames
    # ---------------------------------------------------------

    issue_rows = []
    closed_rows = []

    for difficulty, counts in results.items():

        issue_rows.append(
            {"difficulty": difficulty, "count": counts["total"]}
        )

        closed_rows.append(
            {"difficulty": difficulty, "count": counts["closed"]}
        )

    issue_df = pd.DataFrame(issue_rows)
    closed_df = pd.DataFrame(closed_rows)

    # ---------------------------------------------------------
    # Save CSVs
    # ---------------------------------------------------------

    save_dataframe(
        issue_df,
        DATA_DIR / "python_sdk_issue_difficulty.csv",
    )

    save_dataframe(
        closed_df,
        DATA_DIR / "python_sdk_closed_issue_difficulty.csv",
    )

    # ---------------------------------------------------------
    # Plot pies
    # ---------------------------------------------------------

    plot_pie(
        issue_df,
        label_col="difficulty",
        value_col="count",
        title="Python SDK Issue Difficulty Distribution",
        output_path=CHARTS_DIR / "python_sdk_issue_difficulty_pie.png",
    )

    plot_pie(
        closed_df,
        label_col="difficulty",
        value_col="count",
        title="Python SDK Closed Issue Difficulty Distribution",
        output_path=CHARTS_DIR / "python_sdk_closed_issue_difficulty_pie.png",
    )

    print("\nCharts generated")


if __name__ == "__main__":
    main()