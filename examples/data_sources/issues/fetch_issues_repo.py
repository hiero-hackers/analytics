"""Example script for fetching open and closed issues from a repository."""

from hiero_analytics.config.logging_config import setup_logging
from hiero_analytics.config.paths import ORG, REPO
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import fetch_repo_issues_graphql

setup_logging(modules="hiero_analytics")

REPOSITORY = REPO
ORGANIZATION = ORG

def fetch_issues_in_repo() -> None:
    """Fetch and report open and closed issue counts for one repository."""
    client = GitHubClient()

    open_issues = fetch_repo_issues_graphql(
        client,
        owner=ORGANIZATION,
        repo=REPOSITORY,
        states=["OPEN"],
    )

    closed_issues = fetch_repo_issues_graphql(
        client,
        owner=ORGANIZATION,
        repo=REPOSITORY,
        states=["CLOSED"],
    )

    print(f"Open issues: {len(open_issues)}")
    print(f"Closed issues: {len(closed_issues)}")
    print(f"Total issues: {len(open_issues) + len(closed_issues)}\n")

if __name__ == "__main__":
    fetch_issues_in_repo()
