"""Contributor activity ingestion via the GraphQL API.

Contributor activity combines issue- and PR-lifecycle signals. With a lookback
window it is a bounded rolling fetch; with full history (``lookback_days=None``,
needed for stable yearly aggregates) it is incremental via the dataset store.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hiero_analytics.config.github import GITHUB_MAX_WORKERS
from hiero_analytics.data_sources.queries import load_query

from ..cache import load_records_cache, save_records_cache
from ..github_client import GitHubClient
from ..models import ContributorActivityRecord
from ..pagination import extract_graphql_cursor_page, paginate_cursor
from ._common import (
    _cache_kwargs,
    _parse_graphql_datetime,
    fetch_org_resource_parallel,
)
from .incremental import OrgIncrementalResource, fetch_org_incremental

CONTRIBUTOR_ACTIVITY_RESOURCE = OrgIncrementalResource(
    name="contributor_activity",
    model_class=ContributorActivityRecord,
    # Events are immutable, so identity is the full event tuple and the
    # watermark advances on the event time itself.
    key_of=lambda event: (
        event.repo,
        event.activity_type,
        event.actor,
        event.occurred_at,
        event.target_type,
        event.target_number,
    ),
    updated_at_of=lambda event: event.occurred_at,
    task_desc="contributor activity",
)

_CONTRIBUTOR_ACTIVITY_TYPES = [
    "authored_issue",
    "authored_pull_request",
    "reviewed_pull_request",
    "merged_pull_request",
]


def _fetch_repo_pull_request_activity_graphql(
    client: GitHubClient,
    owner: str,
    repo: str,
    cutoff: datetime | None,
) -> list[ContributorActivityRecord]:
    """Fetch contributor activity signals from pull request lifecycle data.

    PRs are ordered by ``UPDATED_AT`` descending, so once a page contains a PR
    updated before ``cutoff`` we can stop paginating — every later page is older.
    ``from_github_node`` already drops individual events before ``cutoff``.
    """
    contributor_activity_query = load_query("contributor_activity")

    def page(cursor: str | None) -> tuple[list[ContributorActivityRecord], str | None, bool]:
        """Fetch a single page of pull requests, stopping past the cutoff."""
        data = client.graphql(
            contributor_activity_query,
            {"owner": owner, "repo": repo, "cursor": cursor},
        )
        nodes, next_cursor, has_next = extract_graphql_cursor_page(data, ["repository", "pullRequests"])

        records: list[ContributorActivityRecord] = []
        page_has_older_prs = False

        for node in nodes:
            updated_at = _parse_graphql_datetime(node.get("updatedAt"))
            if cutoff is not None and updated_at is not None and updated_at < cutoff:
                page_has_older_prs = True

            records.extend(
                ContributorActivityRecord.from_github_node(
                    node,
                    {
                        "owner": owner,
                        "repo": repo,
                        "cutoff": cutoff,
                        "target_type": "pull_request",
                    },
                )
            )

        return records, next_cursor, has_next and not page_has_older_prs

    return paginate_cursor(page)


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
                        "activity_source": "issue",
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
    refresh: bool = False,
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

    cutoff = datetime.now(UTC) - timedelta(days=lookback_days) if lookback_days is not None else None
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


def _fetch_repo_contributor_activity_at_cutoff(
    client: GitHubClient,
    owner: str,
    repo: str,
    cutoff: datetime | None,
) -> list[ContributorActivityRecord]:
    """Combine a repo's PR and issue contributor-activity at a given cutoff."""
    return [
        *_fetch_repo_pull_request_activity_graphql(client, owner, repo, cutoff),
        *_fetch_repo_issue_activity_graphql(client, owner, repo, cutoff),
    ]


def fetch_org_contributor_activity_graphql(
    client: GitHubClient,
    org: str,
    max_workers: int = GITHUB_MAX_WORKERS,
    *,
    repos: list[str] | None = None,
    lookback_days: int | None = 183,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False,
) -> list[ContributorActivityRecord]:
    """Fetch contributor activity records across all repositories in an organization.

    Dispatches between two distinct modes:

    - ``lookback_days`` set — a bounded rolling window, TTL-cached per repo and
      fetched fresh each run (``repos`` and the cache flags apply here only);
    - ``lookback_days=None`` — full history (needed for stable yearly
      aggregates), fetched **incrementally** via the persistent dataset store.
    """
    if lookback_days is not None:
        return _fetch_org_activity_window(
            client,
            org,
            max_workers,
            repos=repos,
            lookback_days=lookback_days,
            use_cache=use_cache,
            cache_ttl_seconds=cache_ttl_seconds,
            refresh=refresh,
        )
    return _fetch_org_activity_full_history(client, org, max_workers, refresh=refresh)


def _fetch_org_activity_window(
    client: GitHubClient,
    org: str,
    max_workers: int,
    *,
    repos: list[str] | None,
    lookback_days: int,
    use_cache: bool | None,
    cache_ttl_seconds: int | None,
    refresh: bool,
) -> list[ContributorActivityRecord]:
    """Bounded rolling-window fetch: per-repo TTL cache, re-fetched each run."""

    def fetch_func(repo):
        """Fetch contributor activity for a repository."""
        return fetch_repo_contributor_activity_graphql(
            client,
            repo.owner,
            repo.name,
            lookback_days=lookback_days,
            **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
        )

    return fetch_org_resource_parallel(
        client,
        org,
        fetch_func,
        max_workers,
        repos=repos,
        task_desc="contributor activity",
        **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
    )


def _fetch_org_activity_full_history(
    client: GitHubClient,
    org: str,
    max_workers: int,
    *,
    refresh: bool,
) -> list[ContributorActivityRecord]:
    """Full-history incremental fetch via the dataset store (org-wide only)."""

    def full_fetch() -> list[ContributorActivityRecord]:
        return fetch_org_resource_parallel(
            client,
            org,
            lambda repo: _fetch_repo_contributor_activity_at_cutoff(client, repo.owner, repo.name, None),
            max_workers,
            task_desc="contributor activity (full)",
        )

    def since_fetch(since: datetime) -> list[ContributorActivityRecord]:
        return fetch_org_resource_parallel(
            client,
            org,
            lambda repo: _fetch_repo_contributor_activity_at_cutoff(client, repo.owner, repo.name, since),
            max_workers,
            task_desc="contributor activity updates",
        )

    return fetch_org_incremental(
        CONTRIBUTOR_ACTIVITY_RESOURCE,
        org=org,
        full_fetch=full_fetch,
        since_fetch=since_fetch,
        refresh=refresh,
    )
