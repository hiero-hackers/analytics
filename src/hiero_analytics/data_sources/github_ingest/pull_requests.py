"""Merged pull-request difficulty ingestion via the GraphQL API.

Links merged PRs to the issues they close, repo- and org-wide.
"""

from __future__ import annotations

from hiero_analytics.config.github import GITHUB_MAX_WORKERS
from hiero_analytics.config.paths import load_query

from ..github_client import GitHubClient
from ..models import PullRequestDifficultyRecord
from ._common import (
    _cache_kwargs,
    fetch_github_resource,
    fetch_org_resource_parallel,
)


def fetch_repo_merged_pr_difficulty_graphql(
    client: GitHubClient,
    owner: str,
    repo: str,
    *,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False,
) -> list[PullRequestDifficultyRecord]:
    """Fetch merged pull requests and their linked closing issues for a repository."""
    MERGED_PR_QUERY = load_query("merged_pr")
    return fetch_github_resource(
        client,
        MERGED_PR_QUERY,
        {"owner": owner, "repo": repo},
        PullRequestDifficultyRecord,
        ["repository", "pullRequests"],
        cache_key="repo_merged_pr_difficulty",
        cache_scope=f"{owner}_{repo}",
        cache_parameters={"owner": owner, "repo": repo},
        context_builder=lambda _node: {"owner": owner, "repo": repo},
        **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
    )


def fetch_org_merged_pr_difficulty_graphql(
    client: GitHubClient,
    org: str,
    max_workers: int = GITHUB_MAX_WORKERS,
    *,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False,
) -> list[PullRequestDifficultyRecord]:
    """Fetch merged pull request difficulty records across all repositories in an organization."""

    def fetch_func(repo):
        """Fetch merged PR difficulty metrics for a repository."""
        return fetch_repo_merged_pr_difficulty_graphql(
            client, repo.owner, repo.name, **_cache_kwargs(use_cache, cache_ttl_seconds, refresh)
        )

    return fetch_org_resource_parallel(
        client,
        org,
        fetch_func,
        PullRequestDifficultyRecord,
        max_workers,
        "org_merged_pr_difficulty",
        {"org": org},
        task_desc="merged PR difficulty records",
        **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
    )
