"""The shared shape of an org-wide, incrementally fetched resource.

Every org-level dataset follows the same skeleton, planned per repository by
the dataset store (:func:`~hiero_analytics.data_sources.dataset_store.fetch_incremental_by_repo`):
a full fetch for a repository with no state yet (first run, or one that joined
the org later), a guarded since-delta afterwards (a repository that fails holds
its own watermark; any other delta failure falls back to a full fetch of the
same repositories), a periodic full refresh per repository, and persistence. An :class:`OrgIncrementalResource`
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
from operator import attrgetter
from typing import Any

from hiero_analytics.config.github import GITHUB_MAX_WORKERS
from hiero_analytics.config.paths import dataset_path
from hiero_analytics.data_sources.queries import load_query

from ..dataset_store import PartialOrgFetchError, fetch_incremental_by_repo
from ..github_client import GitHubClient
from ..models import RepositoryRecord
from ..usage import usage_scope
from . import _common
from .batched import fetch_org_records_batched

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrgIncrementalResource:
    """Declares an org-wide incrementally fetched resource.

    ``name`` is the dataset-store resource name (the ``dataset_path`` key);
    ``key_of`` gives a record's identity for the incremental upsert;
    ``updated_at_of`` gives the timestamp that advances the watermark;
    ``repo_of`` gives the ``owner/name`` a record belongs to, which is how the
    store keeps state per repository and replaces a repository's rows on its
    full refresh.
    """

    name: str
    model_class: type
    key_of: Callable[[Any], Any]
    updated_at_of: Callable[[Any], datetime | None]
    task_desc: str
    full_refresh_after: timedelta = timedelta(days=30)
    repo_of: Callable[[Any], str] = attrgetter("repo")


def fetch_org_incremental(
    resource: OrgIncrementalResource,
    *,
    client: GitHubClient,
    org: str,
    full_fetch: Callable[[list[RepositoryRecord]], list],
    since_fetch: Callable[[list[RepositoryRecord], datetime], list],
    fingerprint: str = "all",
    refresh: bool = False,
) -> list:
    """Run the shared incremental skeleton for ``resource``.

    ``full_fetch(repos)`` and ``since_fetch(repos, since)`` fetch the given
    repositories; either may raise :class:`PartialOrgFetchError` naming the
    repositories it could not finish, and only those hold their watermark.
    ``since_fetch`` gets the standard guard: any *other* failure falls back to
    a full fetch of the same repositories, so an incremental run is never slower
    or more broken than a full one. The org is listed once, after the offline
    check, so an offline run makes no request.
    """
    listing: dict[str, RepositoryRecord] = {}

    def list_repos() -> list[str]:
        listing.update((repo.full_name, repo) for repo in _common.fetch_org_repos_graphql(client, org))
        return list(listing)

    def repos_named(names: list[str]) -> list[RepositoryRecord]:
        return [listing[name] for name in names]

    def guarded_since(names: list[str], since: datetime) -> list:
        repos = repos_named(names)
        try:
            return since_fetch(repos, since)
        except PartialOrgFetchError:
            raise  # let the store hold those repositories' watermarks; don't fall back to full
        except Exception:
            logger.exception("Incremental %s fetch failed; falling back to full fetch", resource.task_desc)
            return full_fetch(repos)

    with usage_scope(org=org, dataset=resource.name):
        return fetch_incremental_by_repo(
            path=dataset_path(resource.name, org, fingerprint),
            model_class=resource.model_class,
            key_of=resource.key_of,
            updated_at_of=resource.updated_at_of,
            repo_of=resource.repo_of,
            list_repos=list_repos,
            full_fetch=lambda names: full_fetch(repos_named(names)),
            since_fetch=guarded_since,
            confirm_gone=lambda name: _common.repository_is_gone(client, name),
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

    def full_fetch(repos: list[RepositoryRecord]) -> list:
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
            repos=repos,
        )

    def since_fetch(repos: list[RepositoryRecord], since: datetime) -> list:
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
                repos=repos,
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
            repos=repos,
        )

    return fetch_org_incremental(
        resource,
        client=client,
        org=org,
        full_fetch=full_fetch,
        since_fetch=since_fetch,
        fingerprint=fingerprint,
        refresh=refresh,
    )
