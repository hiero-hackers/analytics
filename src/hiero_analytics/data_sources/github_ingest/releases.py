"""GitHub Releases ingestion via GraphQL.

Uses the per-repo TTL cache instead of incremental state because release
histories are small and infrequently updated. Each run performs a full
per-repo fetch when the cache is stale.

GitHub Releases only — no git-tag fallback. Drafts are excluded client-side
because the GraphQL releases connection has no server-side draft filter.

Org-wide fetches batch stale repos into few GraphQL requests (aliased, via
fetch_repos_batched) instead of one request per repo, since a
one-request-per-repo fan-out is unfriendly to the org's API rate limit at
scale. Repos with a fresh cache entry are skipped before any network call
happens at all — a plain disk read via load_records_cache, no request spent
finding out a repo didn't need refetching. A repo a batch fails to return
cleanly falls back to the single-repo path below, which keeps its own
explicit page-count guard: paginate_cursor's own max_pages cutoff stops
silently on overrun rather than signalling truncation, so it isn't used
here for this safety-critical bound.
"""

from __future__ import annotations

from itertools import groupby
from operator import attrgetter

from hiero_analytics.config.github import GITHUB_MAX_WORKERS
from hiero_analytics.data_sources.queries import load_query

from ..cache import load_records_cache, save_records_cache
from ..github_client import GitHubClient
from ..models import ReleaseRecord, RepositoryRecord
from ..pagination import extract_graphql_cursor_page
from ._common import _cache_kwargs, fetch_org_repos_graphql
from .batched import fetch_repos_batched

RELEASES_RESOURCE = "repo_releases"
MAX_RELEASE_PAGES = 100


def _fetch_repo_releases_uncached(client: GitHubClient, owner: str, repo: str) -> list[ReleaseRecord]:
    """The actual network fetch, no cache involved — shared by the single-repo and batch-fallback paths.

    Deliberately not built on ``paginate_cursor``'s own ``max_pages``: that
    cutoff logs a warning and returns whatever was collected so far, with no
    signal to the caller that the result is truncated. The explicit
    for/else below distinguishes "pagination finished naturally" from
    "exhausted MAX_RELEASE_PAGES iterations" and raises in the latter case,
    so a runaway release history is never silently saved as if complete.
    """
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

    return records


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

    records = _fetch_repo_releases_uncached(client, owner, repo)
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

    Cache-first, then a batched fetch for whatever's stale, then a per-repo
    fallback for anything the batch couldn't return cleanly — see the module
    docstring for the full reasoning.
    """
    all_repos = fetch_org_repos_graphql(client, org, **_cache_kwargs(use_cache, cache_ttl_seconds, refresh))
    if repos:
        allowed = set(repos)
        all_repos = [r for r in all_repos if r.full_name in allowed or r.name in allowed]

    cached_records: list[ReleaseRecord] = []
    stale_repos: list[RepositoryRecord] = []
    for repo in all_repos:
        cached = load_records_cache(
            RELEASES_RESOURCE,
            f"{repo.owner}_{repo.name}",
            {"owner": repo.owner, "repo": repo.name},
            ReleaseRecord,
            use_cache=use_cache,
            ttl_seconds=cache_ttl_seconds,
            refresh=refresh,
        )
        if cached is None:
            stale_repos.append(repo)
        else:
            cached_records.extend(cached)

    if not stale_repos:
        return cached_records

    batched_records, failed_repos = fetch_repos_batched(
        client,
        stale_repos,
        query_text=load_query("releases"),
        model_class=ReleaseRecord,
        nodes_path=["releases"],
        context_builder=lambda repo: {"owner": repo.owner, "repo": repo.name},
        max_workers=max_workers,
    )

    # Save each repo's slice back to its own cache entry individually --
    # per-repo granularity, so a future run still gets partial cache hits
    # instead of an all-or-nothing org-wide fetch.
    fresh_records = list(cached_records)
    for repo_name, group in groupby(sorted(batched_records, key=attrgetter("repo")), key=attrgetter("repo")):
        owner, _, name = repo_name.partition("/")
        records = list(group)
        save_records_cache(
            RELEASES_RESOURCE,
            f"{owner}_{name}",
            {"owner": owner, "repo": name},
            ReleaseRecord,
            records,
            use_cache=use_cache,
        )
        fresh_records.extend(records)

    # A batch that fails to return a repo cleanly (missing alias, repeating
    # cursor) falls back to the single-repo path, which keeps its own
    # explicit MAX_RELEASE_PAGES guard -- see _fetch_repo_releases_uncached.
    for repo in failed_repos:
        records = fetch_repo_releases_graphql(
            client,
            repo.owner,
            repo.name,
            **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
        )
        fresh_records.extend(records)

    return fresh_records
