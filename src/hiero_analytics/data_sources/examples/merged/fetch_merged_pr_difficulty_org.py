"""Example script for collecting merged pull request difficulty metrics."""

from hiero_analytics.config.logging_config import setup_logging
from hiero_analytics.config.paths import ORG
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import fetch_org_merged_pr_difficulty_graphql

setup_logging(modules="hiero_analytics")

ORGANIZATION = ORG

def main() -> None:
    """Fetch merged PR difficulty records across the configured organization."""
    client = GitHubClient()

    records = fetch_org_merged_pr_difficulty_graphql(
        client,
        org=ORGANIZATION,
        max_workers=5,
    )

    print(f"Collected {len(records)} merged PR records across {ORGANIZATION}\n")

    for record in records[:5]:

        print(
            record.repo,
            record.pr_number,
            record.pr_additions,
            record.pr_changed_files,
            record.issue_labels,
        )


if __name__ == "__main__":
    main()
