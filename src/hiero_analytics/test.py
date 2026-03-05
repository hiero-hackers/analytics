from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_graphql import fetch_repo_issues_graphql

client = GitHubClient()

issues = fetch_repo_issues_graphql(
    client,
    owner="hiero-ledger",
    repo="hiero-sdk-python",
)

print("Total issues:", len(issues))