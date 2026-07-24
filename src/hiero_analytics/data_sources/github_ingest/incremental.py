"""The shared shape of an org-wide, incrementally fetched resource.

Every org-level dataset follows the same skeleton: a full fetch on first run, a
guarded since-delta afterwards (partial failures hold the watermark; any other
failure falls back to a full fetch), a periodic forced full refresh, and
persistence via the dataset store. An :class:`OrgIncrementalResource`
declaration captures what varies per resource — its dataset name, model, record
identity, and watermark accessor — so adding a resource is one declaration plus
its query plumbing, not another copy of the skeleton.

Batched resources (org fetch via repo-aliased GraphQL) additionally share
:func:`fetch_org_batched_incremental`, which builds both delta styles: a
dedicated ``*_since`` query, or reuse of the base query ordered
``UPDATED_AT``-descending with an early-stop predicate.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from hiero_analytics.config.github import GITHUB_MAX_WORKERS
from hiero_analytics.config.paths import dataset_path
from hiero_analytics.data_sources.queries import load_query

from ..dataset_store import PartialOrgFetchError, fetch_incremental
from ..github_client import GitHubClient
from .batched import fetch_org_records_batched

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrgIncrementalResource:
    """Declares an org-wide incrementally fetched resource.

    ``name`` is the dataset-store resource name (the ``dataset_path`` key);
    ``key_of`` gives a record's identity for the incremental upsert;
    ``updated_at_of`` gives the timestamp that advances the watermark.
    """

    name: str
    model_class: type
    key_of: Callable[[Any], Any]
    updated_at_of: Callable[[Any], datetime | None]
    task_desc: str
    full_refresh_after: timedelta = timedelta(days=30)


def fetch_org_incremental(
    resource: OrgIncrementalResource,
    *,
    org: str,
    full_fetch: Callable[[], list],
    since_fetch: Callable[[datetime], list],
    fingerprint: str = "all",
    refresh: bool = False,
) -> list:
    """Run the shared incremental skeleton for ``resource``.

    Wraps ``since_fetch`` with the standard guard: a partial org fetch
    propagates so the store holds the watermark (the gap is refetched next
    run); any other failure falls back to a full fetch, so an incremental run
    is never slower or more broken than a full one.
    """

    def guarded_since(since: datetime) -> list:
        try:
            return since_fetch(since)
        except PartialOrgFetchError:
            raise  # let the store hold the watermark; don't fall back to full
        except Exception:
            logger.exception("Incremental %s fetch failed; falling back to full fetch", resource.task_desc)
            return full_fetch()

    return fetch_incremental(
        path=dataset_path(resource.name, org, fingerprint),
        model_class=resource.model_class,
        key_of=resource.key_of,
        updated_at_of=resource.updated_at_of,
        full_fetch=full_fetch,
        since_fetch=guarded_since,
        force_full=refresh,
        full_refresh_after=resource.full_refresh_after,
    )


def fetch_org_batched_incremental(
    client: GitHubClient,
    resource: OrgIncrementalResource,
    *,
    org: str,
    query_name: str,
    nodes_path: list[str],
    per_repo: Callable[[Any], list],
    per_repo_since: Callable[[Any, datetime], list],
    since_query_name: str | None = None,
    node_older_than: Callable[[dict, datetime], bool] | None = None,
    variables: dict[str, Any] | None = None,
    fingerprint: str = "all",
    max_workers: int = GITHUB_MAX_WORKERS,
    refresh: bool = False,
) -> list:
    """Incremental fetch for a resource whose org fetch is repo-batched GraphQL.

    Exactly one delta style must be given:

    - ``since_query_name`` — a dedicated query that filters server-side on
      ``since`` (issues-style ``filterBy``); or
    - ``node_older_than`` — reuse the base query, ordered ``UPDATED_AT``
      descending, stopping at the first node the predicate marks older than
      ``since`` (for connections with no ``filterBy: since``; boundary-page
      records are re-sent harmlessly — the merge is an idempotent upsert).

    ``per_repo`` / ``per_repo_since`` are the single-repo fallbacks batching
    uses for oversized repos.
    """
    if (since_query_name is None) == (node_older_than is None):
        raise ValueError("Provide exactly one of since_query_name or node_older_than")

    def full_fetch() -> list:
        return fetch_org_records_batched(
            client,
            org,
            query_text=load_query(query_name),
            model_class=resource.model_class,
            nodes_path=nodes_path,
            variables=variables,
            per_repo=per_repo,
            task_desc=f"organization {resource.task_desc}",
            max_workers=max_workers,
        )

    def since_fetch(since: datetime) -> list:
        task_desc = f"organization {resource.task_desc} updates"
        if since_query_name is not None:
            return fetch_org_records_batched(
                client,
                org,
                query_text=load_query(since_query_name),
                model_class=resource.model_class,
                nodes_path=nodes_path,
                variables={**(variables or {}), "since": since.isoformat()},
                per_repo=lambda repo: per_repo_since(repo, since),
                task_desc=task_desc,
                max_workers=max_workers,
            )
        return fetch_org_records_batched(
            client,
            org,
            query_text=load_query(query_name),
            model_class=resource.model_class,
            nodes_path=nodes_path,
            variables=variables,
            stop_node=lambda node: node_older_than(node, since),
            per_repo=lambda repo: per_repo_since(repo, since),
            task_desc=task_desc,
            max_workers=max_workers,
        )

    return fetch_org_incremental(
        resource,
        org=org,
        full_fetch=full_fetch,
        since_fetch=since_fetch,
        fingerprint=fingerprint,
        refresh=refresh,
    )
