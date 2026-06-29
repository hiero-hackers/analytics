"""Example script for fetching all repositories in a GitHub organization."""

from hiero_analytics.config.logging_config import setup_logging
from hiero_analytics.config.paths import ORG
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import fetch_org_repos_graphql

setup_logging(modules="hiero_analytics")

ORGANIZATION = ORG

def fetch_repos_in_org() -> None:
    """Fetch and print repositories for the configured organization."""
    client = GitHubClient()
    
    repos = fetch_org_repos_graphql(client, ORGANIZATION)

    print(f"Found {len(repos)} repositories in {ORGANIZATION}\n")

    for repo in repos:
        print(repo.full_name)


if __name__ == "__main__":
    fetch_repos_in_org()
