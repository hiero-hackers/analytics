"""Shared engine for GitHub data ingestion.

Generic paginated and parallel fetch primitives plus the repository listing that
the resource-specific modules (``issues``, ``timeline``, ``pull_requests``,
``contributors``) build on. Keeping these here lets each resource module depend
on one shared core without importing one another.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import TypeVar

from hiero_analytics.config.paths import load_query

from ..cache import load_records_cache, save_records_cache
from ..dataset_store import PartialOrgFetchError
from ..github_client import GitHubClient
from ..models import BaseRecord, RepositoryRecord
from ..pagination import extract_graphql_cursor_page, paginate_cursor

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


def _parse_graphql_datetime(value: object) -> datetime | None:
    """Parse an ISO datetime string from a GitHub GraphQL response."""
    if not isinstance(value, str):
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


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


def fetch_org_repos_graphql(
    client: GitHubClient,
    org: str,
    *,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False,
) -> list[RepositoryRecord]:
    """Fetch all repository full names for an organization using GraphQL."""
    REPOS_QUERY = load_query("repos")
    return fetch_github_resource(
        client,
        REPOS_QUERY,
        {"org": org},
        RepositoryRecord,
        ["organization", "repositories"],
        cache_key="org_repos",
        cache_scope=org,
        cache_parameters={"org": org},
        context_builder=lambda _node: {"owner": org},
        **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
    )


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

    all_repos = fetch_org_repos_graphql(client, org, **_cache_kwargs(use_cache, cache_ttl_seconds, refresh))

    if repos:
        allowed = set(repos)
        all_repos = [r for r in all_repos if r.full_name in allowed or r.name in allowed]

    all_records = []
    had_failures = False

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
                had_failures = True
                logger.exception("Failed fetching %s for %s: %s", task_desc, repo.full_name, exc)

    logger.info("Collected %d %s across %s", len(all_records), task_desc, org)
    if had_failures:
        # Don't cache an incomplete org snapshot: a transient repo failure would
        # otherwise be served to every caller until the TTL expires. Return the
        # partial result for this run only; the next run re-fetches and caches.
        logger.warning(
            "Not caching %s for %s: one or more repo fetches failed this run",
            task_desc,
            org,
        )
        return all_records
    save_records_cache(cache_key, org, cache_parameters, model_class, all_records, use_cache=use_cache)
    return all_records


def _run_repo_fetches(
    repos: list,
    max_workers: int,
    per_repo: Callable[[RepositoryRecord], list],
    task_desc: str,
) -> tuple[list, list]:
    """Fetch each repo in parallel; return (records, repos_that_failed)."""
    records: list = []
    failed: list = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(per_repo, repo): repo for repo in repos}
        for future in as_completed(futures):
            repo = futures[future]
            try:
                records.extend(future.result())
            except Exception:
                logger.warning("Failed fetching %s for %s (will retry)", task_desc, repo.full_name)
                failed.append(repo)
    return records, failed


def _fetch_org_records_parallel(
    client: GitHubClient,
    org: str,
    max_workers: int,
    per_repo: Callable[[RepositoryRecord], list],
    task_desc: str,
) -> list:
    """Fan a per-repo fetch across all org repos and collect the results.

    Failed repos are retried once at reduced concurrency. Transient failures
    (spurious 401/403 under load) usually succeed the second time. If any repo is
    still failing after the retry, we raise :class:`PartialOrgFetchError` carrying
    the records that did arrive — the incremental store then merges them but holds
    the watermark, so the missed repos are re-fetched next run rather than skipped
    past (which would freeze them until the periodic full refresh).
    """
    all_repos = fetch_org_repos_graphql(client, org)
    records, failed = _run_repo_fetches(all_repos, max_workers, per_repo, task_desc)

    if failed:
        retry_records, still_failed = _run_repo_fetches(failed, max(1, max_workers // 2), per_repo, task_desc)
        records.extend(retry_records)
        if still_failed:
            names = ", ".join(repo.full_name for repo in still_failed)
            logger.error(
                "Failed fetching %s after retry for: %s; holding watermark so the next run re-covers the gap",
                task_desc,
                names,
            )
            raise PartialOrgFetchError(records, still_failed)

    return records
