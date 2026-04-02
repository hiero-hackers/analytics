"""
GitHub data ingestion utilities using the GraphQL API.

This module provides functions for retrieving repositories, issues, and
merged pull request metadata from GitHub. Data is fetched using cursor-
based pagination and can be aggregated across an organization with
parallel requests to improve ingestion speed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import TypeVar

from .cache import (
    load_records_cache,
    save_records_cache,
)
from .github_client import GitHubClient
from .github_queries import (
    CONTRIBUTOR_ACTIVITY_QUERY,
    CONTRIBUTOR_MERGED_PRS_COUNT_QUERY,
    ISSUES_QUERY,
    MERGED_PR_QUERY,
    REPOS_QUERY,
)
from .models import (
    BaseRecord,
    ContributorActivityRecord,
    ContributorMergedPRCountRecord,
    IssueRecord,
    PullRequestDifficultyRecord,
    RepositoryRecord,
)
from .pagination import extract_graphql_cursor_page, paginate_cursor

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseRecord)


def _cache_kwargs(
    use_cache: bool | None,
    cache_ttl_seconds: int | None,
    refresh: bool,
) -> dict[str, object]:
    """Build keyword arguments for nested cache-aware fetch calls."""
    kwargs: dict[str, object] = {}

    if use_cache is not None:
        kwargs["use_cache"] = use_cache
    if cache_ttl_seconds is not None:
        kwargs["cache_ttl_seconds"] = cache_ttl_seconds
    if refresh:
        kwargs["refresh"] = True

    return kwargs

# --------------------------------------------------------
# GENERIC RESOURCE FETCHER ENGINE
# --------------------------------------------------------


def fetch_github_resource(
    client: GitHubClient,
    query: str,
    variables: dict,
    model_class: type[T],
    nodes_path: list[str],
    *,
    cache_key: str,
    cache_scope: str,
    cache_parameters: dict[str, object],
    context_builder: Callable[[dict], dict] | None = None,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False,
    ) -> list[T]:
    """Generic engine for fetching paginated GitHub resources."""
    cached = load_records_cache(
        cache_key,
        cache_scope,
        cache_parameters,
        model_class,
        use_cache=use_cache,
        ttl_seconds=cache_ttl_seconds,
        refresh=refresh,
    )
    if cached is not None:
        return cached

    def page(cursor: str | None) -> tuple[list[T], str | None, bool]:
        paginated_vars = dict(variables)
        paginated_vars["cursor"] = cursor

        data = client.graphql(query, paginated_vars)
        nodes, next_cursor, has_next = extract_graphql_cursor_page(data, nodes_path)

        items = []
        for node in nodes:
            context = context_builder(node) if context_builder else {}
            result = model_class.from_github_node(node, context)
            items.extend(result)

        return items, next_cursor, has_next

    records = paginate_cursor(page)
    save_records_cache(cache_key, cache_scope, cache_parameters, model_class, records, use_cache=use_cache)
    return records


def fetch_org_resource_parallel(
    client: GitHubClient,
    org: str,
    fetch_repo_func: Callable,
    model_class: type[T],
    max_workers: int,
    cache_key: str,
    cache_parameters: dict[str, object],
    repos: list[str] | None = None,
    *,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False,
    task_desc: str = "records",
) -> list[T]:
    """Generic engine for orchestrating parallel organization repository fetches."""
    cached = load_records_cache(
        cache_key,
        org,
        cache_parameters,
        model_class,
        use_cache=use_cache,
        ttl_seconds=cache_ttl_seconds,
        refresh=refresh,
    )
    if cached is not None:
        return cached

    logger.info("Fetching %s across %s (max_workers=%d)", task_desc, org, max_workers)

    all_repos = fetch_org_repos_graphql(
        client, org, **_cache_kwargs(use_cache, cache_ttl_seconds, refresh)
    )

    if repos:
        allowed = set(repos)
        all_repos = [r for r in all_repos if r.full_name in allowed or r.name in allowed]

    all_records = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_repo_func, repo): repo for repo in all_repos}
        for future in as_completed(futures):
            repo = futures[future]
            try:
                result = future.result()
                if isinstance(result, list):
                    all_records.extend(result)
                else:
                    all_records.append(result)
            except Exception as exc:
                logger.exception("Failed fetching %s for %s: %s", task_desc, repo.full_name, exc)

    logger.info("Collected %d %s across %s", len(all_records), task_desc, org)
    save_records_cache(cache_key, org, cache_parameters, model_class, all_records, use_cache=use_cache)
    return all_records


# --------------------------------------------------------
# FETCH REPOSITORIES
# --------------------------------------------------------

def fetch_org_repos_graphql(
    client: GitHubClient,
    org: str,
    *,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False
    ) -> list[RepositoryRecord]:
    """
    Fetch all repository full names for an organization using GraphQL.
    """
    return fetch_github_resource(
        client, REPOS_QUERY, {"org": org}, RepositoryRecord, ["organization", "repositories"],
        cache_key="org_repos", cache_scope=org, cache_parameters={"org": org},
        context_builder=lambda node: {"owner": org},
        **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
    )

# --------------------------------------------------------
# FETCH ISSUES
# --------------------------------------------------------

def fetch_repo_issues_graphql(
    client: GitHubClient,
    owner: str,
    repo: str,
    states: list[str] | None = None,
    *,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False
    ) -> list[IssueRecord]:
    """Fetch all issues for a repository using GraphQL."""
    norm_states = [s.upper() for s in states] if states else None
    return fetch_github_resource(
        client, ISSUES_QUERY, {"owner": owner, "repo": repo, "states": norm_states}, IssueRecord, ["repository", "issues"],
        cache_key="repo_issues", cache_scope=f"{owner}_{repo}",
        cache_parameters={"owner": owner, "repo": repo, "states": sorted(norm_states or [])},
        context_builder=lambda node: {"owner": owner, "repo": repo},
        **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
    )

def fetch_org_issues_graphql(
    client: GitHubClient,
    org: str,
    states: list[str] | None = None,
    max_workers: int = 5,
    *,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False
    ) -> list[IssueRecord]:
    """Fetch all issues across all repositories in an organization."""
    def fetch_func(repo):
        return fetch_repo_issues_graphql(client, repo.owner, repo.name, states=states, **_cache_kwargs(use_cache, cache_ttl_seconds, refresh))
    return fetch_org_resource_parallel(
        client, org, fetch_func, IssueRecord, max_workers, "org_issues",
        {"org": org, "states": sorted(s.upper() for s in states) if states else []},
        task_desc="organization issues",
        **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
    )

# --------------------------------------------------------
# FETCH MERGED PR DIFFICULTY
# --------------------------------------------------------
def fetch_repo_merged_pr_difficulty_graphql(
    client: GitHubClient,
    owner: str,
    repo: str,
    *,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False
    ) -> list[PullRequestDifficultyRecord]:
    """
    Fetch merged pull requests and their linked closing issues for a repository.
    """
    return fetch_github_resource(
        client, MERGED_PR_QUERY, {"owner": owner, "repo": repo}, PullRequestDifficultyRecord, ["repository", "pullRequests"],
        cache_key="repo_merged_pr_difficulty", cache_scope=f"{owner}_{repo}", 
        cache_parameters={"owner": owner, "repo": repo},
        context_builder=lambda node: {"owner": owner, "repo": repo},
        **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
    )

def fetch_org_merged_pr_difficulty_graphql(
    client: GitHubClient,
    org: str,
    max_workers: int = 5,
    *,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False
    ) -> list[PullRequestDifficultyRecord]:
    """
    Fetch merged pull request difficulty records across all repositories in an organization.
    """
    def fetch_func(repo):
        return fetch_repo_merged_pr_difficulty_graphql(client,
        repo.owner, repo.name, **_cache_kwargs(use_cache, cache_ttl_seconds, refresh))
    return fetch_org_resource_parallel(
        client, org, fetch_func, PullRequestDifficultyRecord, max_workers, "org_merged_pr_difficulty",
        {"org": org}, task_desc="merged PR difficulty records",
        **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
    )

# --------------------------------------------------------
# FETCH CONTRIBUTOR ACTIVITY
# --------------------------------------------------------

def fetch_repo_contributor_activity_graphql(
    client: GitHubClient,
    owner: str,
    repo: str,
    *,
    lookback_days: int = 183,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False
    ) -> list[ContributorActivityRecord]:
    """
    Fetch contributor activity signals from pull request lifecycle data.

    Signals include:
    - authored_pull_request
    - reviewed_pull_request
    - merged_pull_request
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    return fetch_github_resource(
        client, CONTRIBUTOR_ACTIVITY_QUERY, {"owner": owner, "repo": repo}, ContributorActivityRecord, ["repository", "pullRequests"],
        cache_key="repo_contributor_activity", cache_scope=f"{owner}_{repo}",
        cache_parameters={"owner": owner, "repo": repo, "lookback_days": lookback_days},
        context_builder=lambda node: {"owner": owner, "repo": repo, "cutoff": cutoff},
        **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
    )

def fetch_org_contributor_activity_graphql(
    client: GitHubClient,
    org: str,
    max_workers: int = 5,
    *,
    repos: list[str] | None = None,
    lookback_days: int = 183,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False
    ) -> list[ContributorActivityRecord]:
    """
    Fetch contributor activity records across all repositories in an organization.
    """
    def fetch_func(repo):
        return fetch_repo_contributor_activity_graphql(client, repo.owner, repo.name, lookback_days=lookback_days, **_cache_kwargs(use_cache, cache_ttl_seconds, refresh))
    return fetch_org_resource_parallel(
        client, org, fetch_func, ContributorActivityRecord, max_workers, "org_contributor_activity",
        {"org": org, "repos": sorted(repos) if repos else [], "lookback_days": lookback_days}, repos=repos,
        task_desc="contributor activity",
        **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
    )

# --------------------------------------------------------
# FETCH CONTRIBUTOR MERGED PR COUNT
# --------------------------------------------------------

def fetch_repo_contributor_merged_pr_count_graphql(
    client: GitHubClient,
    owner: str,
    repo: str,
    login: str,
    *,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False
    ) -> ContributorMergedPRCountRecord:
    """
    Fetch contributor merged pull request count for a specific user in a repository.
    """
    records = fetch_github_resource(
        client, CONTRIBUTOR_MERGED_PRS_COUNT_QUERY, {"searchQuery": f"is:pr is:merged author:{login} repo:{owner}/{repo}"},
        ContributorMergedPRCountRecord, ["search"],
        cache_key="repo_contributor_merged_pr_count", cache_scope=f"{owner}_{repo}_{login}",
        cache_parameters={"owner": owner, "repo": repo, "login": login},
        context_builder=lambda node: {"owner": owner, "repo": repo, "login": login},
        **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
    )
    return records[0] if records else ContributorMergedPRCountRecord(repo=f"{owner}/{repo}", login=login, merged_pr_count=0)

def fetch_org_contributor_merged_pr_count_graphql(
    client: GitHubClient,
    org: str,
    login: str,
    repos: list[str] | None = None,
    max_workers: int = 5,
    *,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False
    ) -> list[ContributorMergedPRCountRecord]:
    """Fetch contributor merged pull request count for a specific user in an org"""
    def fetch_func(repo):
        return fetch_repo_contributor_merged_pr_count_graphql(client,
        repo.owner, repo.name, login=login,
        **_cache_kwargs(use_cache, cache_ttl_seconds, refresh))
    return fetch_org_resource_parallel(
        client, org, fetch_func, ContributorMergedPRCountRecord,
        max_workers, "org_contributor_merged_pr_count",
        {"org": org, "login": login, "repos": sorted(repos) if repos else []}, repos=repos,
        task_desc=f"merged PR count for {login}",
        **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
    )
