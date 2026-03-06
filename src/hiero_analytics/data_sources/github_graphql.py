"""
This module provides functions to fetch data from the GitHub GraphQL API, including repositories and issues for a given organization. 
It uses pagination to handle large datasets and supports parallel fetching of issues across multiple repositories to speed up the ingestion process.
"""
from __future__ import annotations

from typing import Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from .github_client import GitHubClient
from .pagination import paginate_cursor


# --------------------------------------------------------
# GRAPHQL QUERIES
# --------------------------------------------------------

REPOS_QUERY = """
query($org:String!,$cursor:String){
  organization(login:$org){
    repositories(first:100, after:$cursor){
      pageInfo{
        hasNextPage
        endCursor
      }
      nodes{
        name
      }
    }
  }
}
"""


ISSUES_QUERY = """
query($owner:String!,$repo:String!,$cursor:String){
  repository(owner:$owner,name:$repo){
    issues(first:100, after:$cursor){
      pageInfo{
        hasNextPage
        endCursor
      }
      nodes{
        number
        title
        state
        createdAt
        closedAt
        labels(first:20){
          nodes{
            name
          }
        }
      }
    }
  }
}
"""

MERGED_PR_QUERY = """
query($owner:String!, $repo:String!, $cursor:String) {
  repository(owner:$owner, name:$repo) {
    pullRequests(
      first:100
      after:$cursor
      states:MERGED
      orderBy:{field:UPDATED_AT, direction:DESC}
    ) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        number
        mergedAt
        closingIssuesReferences(first:10) {
          nodes {
            number
            labels(first:20) {
              nodes {
                name
              }
            }
          }
        }
      }
    }
  }
}
"""

# --------------------------------------------------------
# FETCH REPOSITORIES
# --------------------------------------------------------

def fetch_org_repos_graphql(
    client: GitHubClient,
    org: str,
) -> List[str]:

    def page(cursor):

        data = client.graphql(
            REPOS_QUERY,
            {"org": org, "cursor": cursor},
        )

        repo_data = data["data"]["organization"]["repositories"]

        items = [repo["name"] for repo in repo_data["nodes"]]

        next_cursor = repo_data["pageInfo"]["endCursor"]
        has_next = repo_data["pageInfo"]["hasNextPage"]

        return items, next_cursor, has_next

    return paginate_cursor(page)


# --------------------------------------------------------
# FETCH ISSUES FOR ONE REPOSITORY
# --------------------------------------------------------

def fetch_repo_issues_graphql(
    client: GitHubClient,
    owner: str,
    repo: str,
) -> List[dict[str, Any]]:

    def page(cursor):

        data = client.graphql(
            ISSUES_QUERY,
            {
                "owner": owner,
                "repo": repo,
                "cursor": cursor,
            },
        )

        issue_data = data["data"]["repository"]["issues"]

        items = [
            {
                "repo": repo,
                "number": issue["number"],
                "title": issue["title"],
                "state": issue["state"],
                "created_at": issue["createdAt"],
                "closed_at": issue["closedAt"],
                "labels": [
                    label["name"]
                    for label in issue["labels"]["nodes"]
                ],
            }
            for issue in issue_data["nodes"]
        ]

        next_cursor = issue_data["pageInfo"]["endCursor"]
        has_next = issue_data["pageInfo"]["hasNextPage"]

        return items, next_cursor, has_next

    return paginate_cursor(page)


def fetch_repo_merged_pr_difficulty(
    client: GitHubClient,
    owner: str,
    repo: str,
) -> list[dict]:

    def page(cursor):

        data = client.graphql(
            MERGED_PR_QUERY,
            {
                "owner": owner,
                "repo": repo,
                "cursor": cursor,
            },
        )

        pr_data = data["data"]["repository"]["pullRequests"]

        items = []

        for pr in pr_data["nodes"]:

            issues = pr["closingIssuesReferences"]["nodes"]

            for issue in issues:

                labels = [
                    label["name"]
                    for label in issue["labels"]["nodes"]
                ]

                items.append(
                    {
                        "pr": pr["number"],
                        "issue": issue["number"],
                        "labels": labels,
                        "merged_at": pr["mergedAt"],
                    }
                )

        next_cursor = pr_data["pageInfo"]["endCursor"]
        has_next = pr_data["pageInfo"]["hasNextPage"]

        return items, next_cursor, has_next

    return paginate_cursor(page)

# --------------------------------------------------------
# FETCH ALL ISSUES ACROSS AN ORG (PARALLEL)
# --------------------------------------------------------

def fetch_org_issues_graphql(
    client: GitHubClient,
    org: str,
    max_workers: int = 5,
) -> List[dict[str, Any]]:
    """
    Fetch all issues across every repository in an organization.
    Uses parallel fetching to speed up ingestion.
    """

    repos = fetch_org_repos_graphql(client, org)

    all_issues: List[dict[str, Any]] = []

    def fetch(repo: str):
        print(f"Scanning repository: {repo}")
        return fetch_repo_issues_graphql(
            client,
            owner=org,
            repo=repo,
        )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:

        futures = {
            executor.submit(fetch, repo): repo
            for repo in repos
        }

        for future in as_completed(futures):

            repo = futures[future]

            try:
                repo_issues = future.result()
                all_issues.extend(repo_issues)

            except Exception as e:
                print(f"Failed fetching {repo}: {e}")

    return all_issues