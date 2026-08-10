"""GitHub Releases ingestion via GraphQL.

Uses the per-repo TTL cache instead of incremental state because release
histories are small and infrequently updated. Each run performs a full
per-repo fetch when the cache is stale.

GitHub Releases only — no git-tag fallback. Drafts are excluded client-side
because the GraphQL releases connection has no server-side draft filter.
"""

from __future__ import annotations

from hiero_analytics.config.github import GITHUB_MAX_WORKERS
from hiero_analytics.data_sources.queries import load_query

from ..cache import load_records_cache, save_records_cache
from ..github_client import GitHubClient
from ..models import ReleaseRecord
from ..pagination import extract_graphql_cursor_page
from ._common import _cache_kwargs, fetch_org_resource_parallel

RELEASES_RESOURCE = "repo_releases"
MAX_RELEASE_PAGES = 100


def fetch_repo_releases_graphql(
    client: GitHubClient,
    owner: str,
    repo: str,
    *,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False,
) -> list[ReleaseRecord]:
    """Fetch every published, non-draft release for one repository.

    GitHub orders the connection by ``CREATED_AT`` descending, but pagination
    always runs to completion — releases are cheap enough per repo that there
    is no early-stop cutoff, unlike the high-volume PR/issue fetchers.
    """
    cache_scope = f"{owner}_{repo}"
    cache_parameters = {"owner": owner, "repo": repo}
    cached = load_records_cache(
        RELEASES_RESOURCE,
        cache_scope,
        cache_parameters,
        ReleaseRecord,
        use_cache=use_cache,
        ttl_seconds=cache_ttl_seconds,
        refresh=refresh,
    )
    if cached is not None:
        return cached

    releases_query = load_query("releases")

    def page(cursor: str | None) -> tuple[list[ReleaseRecord], str | None, bool]:
        """Fetch a single page of releases."""
        data = client.graphql(releases_query, {"owner": owner, "repo": repo, "cursor": cursor})
        nodes, next_cursor, has_next = extract_graphql_cursor_page(data, ["repository", "releases"])
        records = [
            record for node in nodes for record in ReleaseRecord.from_github_node(node, {"owner": owner, "repo": repo})
        ]
        return records, next_cursor, has_next

    records: list[ReleaseRecord] = []
    cursor: str | None = None

    for _ in range(MAX_RELEASE_PAGES):
        page_records, cursor, has_next = page(cursor)
        records.extend(page_records)

        if not has_next:
            break
    else:
        raise RuntimeError(
            f"Release history for {owner}/{repo} exceeds {MAX_RELEASE_PAGES} pages; refusing to emit partial data."
        )

    save_records_cache(RELEASES_RESOURCE, cache_scope, cache_parameters, ReleaseRecord, records, use_cache=use_cache)
    return records


def fetch_org_releases_graphql(
    client: GitHubClient,
    org: str,
    max_workers: int = GITHUB_MAX_WORKERS,
    *,
    repos: list[str] | None = None,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False,
) -> list[ReleaseRecord]:
    """Fetch releases across every repository in an organization.

    Full per-repo refetch every run, cache permitting — see the module
    docstring for why this resource isn't incremental.
    """

    def fetch_func(repo):
        """Fetch releases for a single repository."""
        return fetch_repo_releases_graphql(
            client,
            repo.owner,
            repo.name,
            **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
        )

    return fetch_org_resource_parallel(
        client,
        org,
        fetch_func,
        max_workers,
        repos=repos,
        task_desc="releases",
        **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
    )
