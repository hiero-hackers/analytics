"""Contributor activity and merged-PR-count ingestion via the GraphQL API.

Contributor activity combines issue- and PR-lifecycle signals. With a lookback
window it is a bounded rolling fetch; with full history (``lookback_days=None``,
needed for stable yearly aggregates) it is incremental via the dataset store.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from hiero_analytics.config.github import GITHUB_MAX_WORKERS
from hiero_analytics.config.paths import dataset_path, load_query

from ..cache import load_records_cache, save_records_cache
from ..dataset_store import PartialOrgFetchError, fetch_incremental
from ..github_client import GitHubClient
from ..models import ContributorActivityRecord, ContributorMergedPRCountRecord
from ..pagination import extract_graphql_cursor_page, paginate_cursor
from ._common import (
    _cache_kwargs,
    _fetch_org_records_parallel,
    _parse_graphql_datetime,
    fetch_github_resource,
    fetch_org_resource_parallel,
)

logger = logging.getLogger(__name__)

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

    With ``lookback_days`` set this is a bounded rolling window, fetched fresh
    each run. With ``lookback_days=None`` (full history — needed for stable yearly
    aggregates) it is **incremental**: the persistent dataset store keeps the full
    history, and later runs fetch only activity since the watermark (using the
    watermark as the pagination cutoff) and merge it in. The since-fetch falls
    back to a full fetch on error; ``refresh=True`` forces a full re-fetch.
    """
    if lookback_days is not None:

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
            ContributorActivityRecord,
            max_workers,
            "org_contributor_activity",
            {
                "org": org,
                "repos": sorted(repos) if repos else [],
                "lookback_days": lookback_days,
                "activity_types": _CONTRIBUTOR_ACTIVITY_TYPES,
            },
            repos=repos,
            task_desc="contributor activity",
            **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
        )

    # Full history -> incremental (org-wide; the repos subset filter is only
    # honoured for the bounded-window path above).
    def full_fetch() -> list[ContributorActivityRecord]:
        return _fetch_org_records_parallel(
            client,
            org,
            max_workers,
            lambda repo: _fetch_repo_contributor_activity_at_cutoff(client, repo.owner, repo.name, None),
            "contributor activity (full)",
        )

    def since_fetch(since: datetime) -> list[ContributorActivityRecord]:
        try:
            return _fetch_org_records_parallel(
                client,
                org,
                max_workers,
                lambda repo: _fetch_repo_contributor_activity_at_cutoff(client, repo.owner, repo.name, since),
                "contributor activity updates",
            )
        except PartialOrgFetchError:
            raise  # let the store hold the watermark; don't fall back to full
        except Exception:
            logger.exception("Incremental contributor-activity fetch failed; falling back to full fetch")
            return full_fetch()

    return fetch_incremental(
        path=dataset_path("contributor_activity", org, "all"),
        model_class=ContributorActivityRecord,
        key_of=lambda e: (e.repo, e.activity_type, e.actor, e.occurred_at, e.target_type, e.target_number),
        updated_at_of=lambda e: e.occurred_at,
        full_fetch=full_fetch,
        since_fetch=since_fetch,
        force_full=refresh,
        full_refresh_after=timedelta(days=30),
    )


def fetch_repo_contributor_merged_pr_count_graphql(
    client: GitHubClient,
    owner: str,
    repo: str,
    login: str,
    *,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False,
) -> ContributorMergedPRCountRecord:
    """Fetch contributor merged pull request count for a specific user in a repository."""
    CONTRIBUTOR_MERGED_PRS_COUNT_QUERY = load_query("contributor_merged_prs_count")
    records = fetch_github_resource(
        client,
        CONTRIBUTOR_MERGED_PRS_COUNT_QUERY,
        {"searchQuery": f"is:pr is:merged author:{login} repo:{owner}/{repo}"},
        ContributorMergedPRCountRecord,
        ["search"],
        cache_key="repo_contributor_merged_pr_count",
        cache_scope=f"{owner}_{repo}_{login}",
        cache_parameters={"owner": owner, "repo": repo, "login": login},
        context_builder=lambda _node: {"owner": owner, "repo": repo, "login": login},
        **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
    )
    return (
        records[0]
        if records
        else ContributorMergedPRCountRecord(repo=f"{owner}/{repo}", login=login, merged_pr_count=0)
    )


def fetch_org_contributor_merged_pr_count_graphql(
    client: GitHubClient,
    org: str,
    login: str,
    repos: list[str] | None = None,
    max_workers: int = GITHUB_MAX_WORKERS,
    *,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False,
) -> list[ContributorMergedPRCountRecord]:
    """Fetch contributor merged pull request count for a specific user in an org."""

    def fetch_func(repo):
        """Fetch merged PR counts for a contributor in a repository."""
        return fetch_repo_contributor_merged_pr_count_graphql(
            client, repo.owner, repo.name, login=login, **_cache_kwargs(use_cache, cache_ttl_seconds, refresh)
        )

    return fetch_org_resource_parallel(
        client,
        org,
        fetch_func,
        ContributorMergedPRCountRecord,
        max_workers,
        "org_contributor_merged_pr_count",
        {"org": org, "login": login, "repos": sorted(repos) if repos else []},
        repos=repos,
        task_desc=f"merged PR count for {login}",
        **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
    )
