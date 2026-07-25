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

from hiero_analytics.data_sources.queries import load_query

from ..cache import load_records_cache, save_records_cache
from ..dataset_store import PartialOrgFetchError
from ..github_client import GitHubClient
from ..models import BaseRecord, RepositoryRecord
from ..pagination import extract_graphql_cursor_page, paginate_cursor
from ..serialization import parse_github_datetime

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
    """Parse an ISO datetime from a GraphQL response (lenient: malformed is None)."""
    return parse_github_datetime(value)


def node_older_than(node: dict, since: datetime) -> bool:
    """Early-stop predicate for ``UPDATED_AT``-descending PR pagination.

    Shared by every pull-request resource: ``pullRequests`` has no
    ``filterBy: since``, so a delta walks pages newest-first and stops at the
    first node last updated before the watermark.
    """
    updated_at = _parse_graphql_datetime(node.get("updatedAt"))
    return updated_at is not None and updated_at < since


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


def fetch_org_resource_parallel(
    client: GitHubClient,
    org: str,
    fetch_repo_func: Callable,
    max_workers: int,
    repos: list[str] | None = None,
    *,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False,
    task_desc: str = "records",
) -> list:
    """Generic engine for orchestrating parallel organization repository fetches.

    Caching happens only at the per-repo layer (inside ``fetch_repo_func``), so the
    TTL there is the single staleness bound. There is deliberately no org-level
    records cache: stamping an assembled snapshot with a fresh timestamp would
    launder the age of per-repo entries that are already up to a TTL old.

    Raises :class:`PartialOrgFetchError` when any repo still fails after a retry,
    so callers never receive an incomplete org snapshot.
    """
    logger.info("Fetching %s across %s (max_workers=%d)", task_desc, org, max_workers)

    all_repos = fetch_org_repos_graphql(client, org, **_cache_kwargs(use_cache, cache_ttl_seconds, refresh))

    if repos:
        allowed = set(repos)
        all_repos = [r for r in all_repos if r.full_name in allowed or r.name in allowed]

    def per_repo(repo: RepositoryRecord) -> list:
        result = fetch_repo_func(repo)
        return result if isinstance(result, list) else [result]

    all_records = fetch_all_with_retry(all_repos, max_workers, per_repo, task_desc)

    logger.info("Collected %d %s across %s", len(all_records), task_desc, org)
    return all_records


def _describe_item(item: object) -> str:
    """Human-readable label for a fetch item (repo record, issue, or plain string)."""
    full_name = getattr(item, "full_name", None)
    return full_name if isinstance(full_name, str) else str(item)


def _run_item_fetches(
    items: list,
    max_workers: int,
    per_item: Callable[[object], list],
    task_desc: str,
    describe: Callable[[object], str],
) -> tuple[list, list]:
    """Fetch each item in parallel; return (records, items_that_failed)."""
    records: list = []
    failed: list = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(per_item, item): item for item in items}
        for future in as_completed(futures):
            item = futures[future]
            try:
                records.extend(future.result())
            except Exception:
                logger.warning("Failed fetching %s for %s (will retry)", task_desc, describe(item))
                failed.append(item)
    return records, failed


def fetch_all_with_retry(
    items: list,
    max_workers: int,
    per_item: Callable[[object], list],
    task_desc: str,
    describe: Callable[[object], str] = _describe_item,
) -> list:
    """Fan a per-item fetch across all items; retry failures once, never return partial data.

    Failed items are retried once at reduced concurrency. Transient failures
    (spurious 401/403 under load) usually succeed the second time. If any item is
    still failing after the retry, we raise :class:`PartialOrgFetchError` carrying
    the records that did arrive — callers must not treat the result as a complete
    snapshot unless this returns normally.
    """
    records, failed = _run_item_fetches(items, max_workers, per_item, task_desc, describe)

    if failed:
        retry_records, still_failed = _run_item_fetches(failed, max(1, max_workers // 2), per_item, task_desc, describe)
        records.extend(retry_records)
        if still_failed:
            names = ", ".join(describe(item) for item in still_failed)
            logger.error(
                "Failed fetching %s after retry for: %s",
                task_desc,
                names,
            )
            raise PartialOrgFetchError(records, still_failed)

    return records
