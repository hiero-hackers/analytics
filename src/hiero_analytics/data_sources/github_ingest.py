"""GitHub data ingestion utilities using the GraphQL API.

This module provides functions for retrieving repositories, issues, and
merged pull request metadata from GitHub. Data is fetched using cursor-
based pagination and can be aggregated across an organization with
parallel requests to improve ingestion speed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from typing import TypeVar

import requests

from hiero_analytics.config.github import BASE_URL
from hiero_analytics.config.paths import load_query

from .cache import load_records_cache, save_records_cache
from .github_client import GitHubClient
from .models import (
    BaseRecord,
    ContributorActivityRecord,
    ContributorMergedPRCountRecord,
    IssueRecord,
    IssueTimelineEventRecord,
    PullRequestDifficultyRecord,
    RepositoryRecord,
)
from .pagination import extract_graphql_cursor_page, paginate_cursor

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseRecord)
_CONTRIBUTOR_ACTIVITY_TYPES = [
    "authored_issue",
    "authored_pull_request",
    "reviewed_pull_request",
    "merged_pull_request",
]
_ISSUE_TIMELINE_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

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


def _parse_graphql_datetime(value: object) -> datetime | None:
    """Parse an ISO datetime string from a GitHub GraphQL response."""
    if not isinstance(value, str):
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

# --------------------------------------------------------
# GENERIC RESOURCE FETCHER ENGINE
# --------------------------------------------------------


def fetch_github_resource(  # noqa: UP047
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
        """Fetch a single page of GraphQL results."""
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


def fetch_org_resource_parallel(  # noqa: UP047
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
    """Fetch all repository full names for an organization using GraphQL."""
    REPOS_QUERY = load_query("repos")
    return fetch_github_resource(
        client, REPOS_QUERY, {"org": org}, RepositoryRecord, ["organization", "repositories"],
        cache_key="org_repos", cache_scope=org, cache_parameters={"org": org},
        context_builder=lambda _node: {"owner": org},
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
    ISSUES_QUERY = load_query("issues")
    norm_states = [s.upper() for s in states] if states else None
    return fetch_github_resource(
        client, ISSUES_QUERY, {"owner": owner, "repo": repo, "states": norm_states}, IssueRecord, ["repository", "issues"],
        cache_key="repo_issues", cache_scope=f"{owner}_{repo}",
        cache_parameters={"owner": owner, "repo": repo, "states": sorted(norm_states or [])},
        context_builder=lambda _node: {"owner": owner, "repo": repo},
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
        """Fetch issues for a single repository."""
        return fetch_repo_issues_graphql(client, repo.owner, repo.name, states=states, **_cache_kwargs(use_cache, cache_ttl_seconds, refresh))
    return fetch_org_resource_parallel(
        client, org, fetch_func, IssueRecord, max_workers, "org_issues",
        {"org": org, "states": sorted(s.upper() for s in states) if states else []},
        task_desc="organization issues",
        **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
    )


def fetch_repo_issue_label_events_graphql(
    client: GitHubClient,
    owner: str,
    repo: str,
    states: list[str] | None = None,
    *,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False,
) -> list[IssueTimelineEventRecord]:
    """Fetch label add/remove events for a repo's issues via GraphQL ``timelineItems``.

    Unlike the repo-wide ``/issues/events`` REST endpoint (which streams every
    event type for every issue and is page-capped), this requests only
    ``LABELED_EVENT``/``UNLABELED_EVENT`` items inline with the issue list, so it
    transfers a fraction of the data, never truncates, and is cached on a stable
    key (owner/repo/states) rather than a per-run ``since`` timestamp.
    """
    query = load_query("issue_label_events")
    norm_states = [s.upper() for s in states] if states else None
    return fetch_github_resource(
        client,
        query,
        {"owner": owner, "repo": repo, "states": norm_states},
        IssueTimelineEventRecord,
        ["repository", "issues"],
        cache_key="repo_issue_label_events",
        cache_scope=f"{owner}_{repo}",
        cache_parameters={"owner": owner, "repo": repo, "states": sorted(norm_states or [])},
        context_builder=lambda _node: {"owner": owner, "repo": repo},
        **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
    )


def fetch_org_issue_label_events_graphql(
    client: GitHubClient,
    org: str,
    states: list[str] | None = None,
    max_workers: int = 5,
    *,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False,
) -> list[IssueTimelineEventRecord]:
    """Fetch label add/remove events for all issues across an organization via GraphQL."""
    def fetch_func(repo):
        """Fetch label events for a single repository."""
        return fetch_repo_issue_label_events_graphql(
            client, repo.owner, repo.name, states=states,
            **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
        )

    return fetch_org_resource_parallel(
        client, org, fetch_func, IssueTimelineEventRecord, max_workers, "org_issue_label_events",
        {"org": org, "states": sorted(s.upper() for s in states) if states else []},
        task_desc="organization issue label events",
        **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
    )


def fetch_repo_issue_timeline_events_rest(
    client: GitHubClient,
    owner: str,
    repo: str,
    issue_number: int,
    *,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False,
) -> list[IssueTimelineEventRecord]:
    """Fetch REST timeline events for one issue."""
    cache_scope = f"{owner}_{repo}_{issue_number}"
    cache_parameters = {
        "owner": owner,
        "repo": repo,
        "issue_number": issue_number,
    }
    cached = load_records_cache(
        "repo_issue_timeline_events",
        cache_scope,
        cache_parameters,
        IssueTimelineEventRecord,
        use_cache=use_cache,
        ttl_seconds=cache_ttl_seconds,
        refresh=refresh,
    )
    if cached is not None:
        return cached

    records: list[IssueTimelineEventRecord] = []
    page = 1

    while True:
        payload = client.get(
            f"{BASE_URL}/repos/{owner}/{repo}/issues/{issue_number}/timeline",
            params={"per_page": 100, "page": page},
            headers=_ISSUE_TIMELINE_HEADERS,
        )

        if not isinstance(payload, list):
            raise ValueError("Issue timeline payload must be a list")

        for event in payload:
            if not isinstance(event, dict):
                continue

            record = IssueTimelineEventRecord.from_rest_event(
                event,
                owner=owner,
                repo=repo,
                issue_number=issue_number,
            )
            if record is not None:
                records.append(record)

        if len(payload) < 100:
            break

        page += 1

    save_records_cache(
        "repo_issue_timeline_events",
        cache_scope,
        cache_parameters,
        IssueTimelineEventRecord,
        records,
        use_cache=use_cache,
    )
    return records


def fetch_issue_timeline_events_rest(
    client: GitHubClient,
    issues: list[IssueRecord],
    *,
    max_workers: int = 8,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False,
) -> list[IssueTimelineEventRecord]:
    """Fetch timeline events for a provided issue collection in parallel."""
    unique_issues = {(issue.repo, issue.number): issue for issue in issues}

    def fetch_func(issue: IssueRecord) -> list[IssueTimelineEventRecord]:
        """Fetch timeline events for a single issue."""
        owner, repo = issue.repo.split("/", maxsplit=1)
        return fetch_repo_issue_timeline_events_rest(
            client,
            owner,
            repo,
            issue.number,
            **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
        )

    records: list[IssueTimelineEventRecord] = []
    issue_items = list(unique_issues.values())

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_func, issue): issue for issue in issue_items}
        for future in as_completed(futures):
            issue = futures[future]
            try:
                records.extend(future.result())
            except Exception as exc:
                logger.exception(
                    "Failed fetching issue timeline events for %s#%s: %s",
                    issue.repo,
                    issue.number,
                    exc,
                )

    return records


def fetch_repo_issue_events_rest_since(
    client: GitHubClient,
    owner: str,
    repo: str,
    *,
    since: datetime,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False,
) -> list[IssueTimelineEventRecord]:
    """Fetch repository issue events since a cutoff date."""
    max_pages = 300
    cutoff = since.astimezone(UTC)
    cutoff_iso = cutoff.isoformat()
    cache_scope = f"{owner}_{repo}"
    cache_parameters = {
        "owner": owner,
        "repo": repo,
        "since": cutoff_iso,
    }
    cached = load_records_cache(
        "repo_issue_events_since",
        cache_scope,
        cache_parameters,
        IssueTimelineEventRecord,
        use_cache=use_cache,
        ttl_seconds=cache_ttl_seconds,
        refresh=refresh,
    )
    if cached is not None:
        return cached

    records: list[IssueTimelineEventRecord] = []
    page = 1

    while True:
        if page > max_pages:
            logger.warning(
                "Stopping issue event pagination for %s/%s after %d pages",
                owner,
                repo,
                max_pages,
            )
            break

        try:
            payload = client.get(
                f"{BASE_URL}/repos/{owner}/{repo}/issues/events",
                params={"per_page": 100, "page": page},
                headers=_ISSUE_TIMELINE_HEADERS,
            )
        except requests.HTTPError as exc:
            response = exc.response
            if response is not None and response.status_code == 422:
                logger.warning(
                    "Stopping issue event pagination for %s/%s at page %d due to 422",
                    owner,
                    repo,
                    page,
                )
                break
            raise

        if not isinstance(payload, list):
            raise ValueError("Repository issue events payload must be a list")

        page_has_older_events = False

        for event in payload:
            if not isinstance(event, dict):
                continue

            issue_node = event.get("issue")
            if not isinstance(issue_node, dict):
                continue

            issue_number = issue_node.get("number")
            if not isinstance(issue_number, int):
                continue

            record = IssueTimelineEventRecord.from_rest_event(
                event,
                owner=owner,
                repo=repo,
                issue_number=issue_number,
            )
            if record is None:
                continue

            occurred_at = record.occurred_at.astimezone(UTC)
            if occurred_at < cutoff:
                page_has_older_events = True
                continue

            records.append(record)

        if len(payload) < 100 or page_has_older_events:
            break

        page += 1

    save_records_cache(
        "repo_issue_events_since",
        cache_scope,
        cache_parameters,
        IssueTimelineEventRecord,
        records,
        use_cache=use_cache,
    )
    return records


def fetch_repo_issue_events_for_issues_since(
    client: GitHubClient,
    issues: list[IssueRecord],
    *,
    since: datetime,
    max_workers: int = 5,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False,
) -> list[IssueTimelineEventRecord]:
    """Fetch repository-level issue events since a cutoff for repos present in the issue set."""
    repos = sorted({issue.repo for issue in issues})

    def fetch_func(full_repo: str) -> list[IssueTimelineEventRecord]:
        """Fetch timeline events for all issues in a repository."""
        owner, repo = full_repo.split("/", maxsplit=1)
        return fetch_repo_issue_events_rest_since(
            client,
            owner,
            repo,
            since=since,
            **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
        )

    records: list[IssueTimelineEventRecord] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_func, full_repo): full_repo for full_repo in repos}
        for future in as_completed(futures):
            full_repo = futures[future]
            try:
                records.extend(future.result())
            except Exception as exc:
                logger.exception(
                    "Failed fetching repository issue events for %s since %s: %s",
                    full_repo,
                    since.isoformat(),
                    exc,
                )

    return records


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
    """Fetch merged pull requests and their linked closing issues for a repository."""
    MERGED_PR_QUERY = load_query("merged_pr")
    return fetch_github_resource(
        client, MERGED_PR_QUERY, {"owner": owner, "repo": repo}, PullRequestDifficultyRecord, ["repository", "pullRequests"],
        cache_key="repo_merged_pr_difficulty", cache_scope=f"{owner}_{repo}", 
        cache_parameters={"owner": owner, "repo": repo},
        context_builder=lambda _node: {"owner": owner, "repo": repo},
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
    """Fetch merged pull request difficulty records across all repositories in an organization."""
    def fetch_func(repo):
        """Fetch merged PR difficulty metrics for a repository."""
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

def _fetch_repo_pull_request_activity_graphql(
    client: GitHubClient,
    owner: str,
    repo: str,
    cutoff: datetime | None,
) -> list[ContributorActivityRecord]:
    """Fetch contributor activity signals from pull request lifecycle data."""
    contributor_activity_query = load_query("contributor_activity")
    return fetch_github_resource(
        client,
        contributor_activity_query,
        {"owner": owner, "repo": repo},
        ContributorActivityRecord,
        ["repository", "pullRequests"],
        cache_key="repo_contributor_pull_request_activity",
        cache_scope=f"{owner}_{repo}",
        cache_parameters={"owner": owner, "repo": repo},
        context_builder=lambda _node: {
            "owner": owner,
            "repo": repo,
            "cutoff": cutoff,
            "target_type": "pull_request",
        },
        use_cache=False,
    )


def _fetch_repo_issue_activity_graphql(
    client: GitHubClient,
    owner: str,
    repo: str,
    cutoff: datetime | None,
) -> list[ContributorActivityRecord]:
    """Fetch contributor activity signals from recently opened issues."""
    contributor_issue_activity_query = load_query("contributor_issue_activity")

    def page(cursor: str | None) -> tuple[list[ContributorActivityRecord], str | None, bool]:
        """Fetch a single page of issues."""
        data = client.graphql(
            contributor_issue_activity_query,
            {"owner": owner, "repo": repo, "cursor": cursor},
        )
        nodes, next_cursor, has_next = extract_graphql_cursor_page(data, ["repository", "issues"])

        records: list[ContributorActivityRecord] = []
        page_has_older_issues = False

        for node in nodes:
            created_at = _parse_graphql_datetime(node.get("createdAt"))
            if cutoff is not None and created_at is not None and created_at < cutoff:
                page_has_older_issues = True

            records.extend(
                ContributorActivityRecord.from_github_node(
                    node,
                    {
                        "owner": owner,
                        "repo": repo,
                        "cutoff": cutoff,
                        "target_type": "issue",
                    },
                )
            )

        return records, next_cursor, has_next and not page_has_older_issues

    return paginate_cursor(page)


def fetch_repo_contributor_activity_graphql(
    client: GitHubClient,
    owner: str,
    repo: str,
    *,
    lookback_days: int | None = 183,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False
    ) -> list[ContributorActivityRecord]:
    """Fetch contributor activity signals from recent issue and PR lifecycle data.

    Issue activity (issues opened by a contributor) and pull request
    activity (PRs authored, reviewed, or merged) are combined into a
    single stream of ``ContributorActivityRecord`` instances.

    When ``lookback_days`` is *None* all historical activity
    is returned, which is required for stable yearly aggregate charts.

    Signals include:
    - authored_issue (issues opened within the lookback window)
    - authored_pull_request
    - reviewed_pull_request
    - merged_pull_request
    """
    cache_scope = f"{owner}_{repo}"
    cache_parameters = {
        "owner": owner,
        "repo": repo,
        "lookback_days": lookback_days,
        "activity_types": _CONTRIBUTOR_ACTIVITY_TYPES,
    }
    cached = load_records_cache(
        "repo_contributor_activity",
        cache_scope,
        cache_parameters,
        ContributorActivityRecord,
        use_cache=use_cache,
        ttl_seconds=cache_ttl_seconds,
        refresh=refresh,
    )
    if cached is not None:
        return cached

    cutoff = (
        datetime.now(UTC) - timedelta(days=lookback_days)
        if lookback_days is not None
        else None
    )
    records = [
        *_fetch_repo_pull_request_activity_graphql(client, owner, repo, cutoff),
        *_fetch_repo_issue_activity_graphql(client, owner, repo, cutoff),
    ]

    save_records_cache(
        "repo_contributor_activity",
        cache_scope,
        cache_parameters,
        ContributorActivityRecord,
        records,
        use_cache=use_cache,
    )
    return records

def fetch_org_contributor_activity_graphql(
    client: GitHubClient,
    org: str,
    max_workers: int = 5,
    *,
    repos: list[str] | None = None,
    lookback_days: int | None = 183,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False
    ) -> list[ContributorActivityRecord]:
    """Fetch contributor activity records across all repositories in an organization.

    Pass ``lookback_days=None`` to retrieve the full history, which is
    necessary for yearly aggregation charts where past counts must remain
    stable across refreshes.
    """
    def fetch_func(repo):
        """Fetch contributor activity for a repository."""
        return fetch_repo_contributor_activity_graphql(client, repo.owner, repo.name, lookback_days=lookback_days, **_cache_kwargs(use_cache, cache_ttl_seconds, refresh))
    return fetch_org_resource_parallel(
        client, org, fetch_func, ContributorActivityRecord, max_workers, "org_contributor_activity",
        {
            "org": org,
            "repos": sorted(repos) if repos else [],
            "lookback_days": lookback_days,
            "activity_types": _CONTRIBUTOR_ACTIVITY_TYPES,
        }, repos=repos,
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
    """Fetch contributor merged pull request count for a specific user in a repository."""
    CONTRIBUTOR_MERGED_PRS_COUNT_QUERY = load_query("contributor_merged_prs_count")
    records = fetch_github_resource(
        client, CONTRIBUTOR_MERGED_PRS_COUNT_QUERY, {"searchQuery": f"is:pr is:merged author:{login} repo:{owner}/{repo}"},
        ContributorMergedPRCountRecord, ["search"],
        cache_key="repo_contributor_merged_pr_count", cache_scope=f"{owner}_{repo}_{login}",
        cache_parameters={"owner": owner, "repo": repo, "login": login},
        context_builder=lambda _node: {"owner": owner, "repo": repo, "login": login},
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
    """Fetch contributor merged pull request count for a specific user in an org."""
    def fetch_func(repo):
        """Fetch merged PR counts for a contributor in a repository."""
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
