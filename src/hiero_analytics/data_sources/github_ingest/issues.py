"""Issue ingestion via the GraphQL API.

Repo- and org-level issue fetching plus issue label add/remove events. The
org-level fetchers are incremental: the persistent dataset store keeps the full
history and later runs fetch only the delta since the watermark.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from hiero_analytics.config.github import GITHUB_MAX_WORKERS
from hiero_analytics.config.paths import dataset_path, load_query

from ..dataset_store import PartialOrgFetchError, fetch_incremental
from ..github_client import GitHubClient
from ..models import IssueRecord, IssueTimelineEventRecord
from ._common import (
    _cache_kwargs,
    _fetch_org_records_parallel,
    fetch_github_resource,
)

logger = logging.getLogger(__name__)


def fetch_repo_issues_graphql(
    client: GitHubClient,
    owner: str,
    repo: str,
    states: list[str] | None = None,
    *,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False,
) -> list[IssueRecord]:
    """Fetch all issues for a repository using GraphQL."""
    ISSUES_QUERY = load_query("issues")
    norm_states = [s.upper() for s in states] if states else None
    return fetch_github_resource(
        client,
        ISSUES_QUERY,
        {"owner": owner, "repo": repo, "states": norm_states},
        IssueRecord,
        ["repository", "issues"],
        cache_key="repo_issues",
        cache_scope=f"{owner}_{repo}",
        cache_parameters={"owner": owner, "repo": repo, "states": sorted(norm_states or [])},
        context_builder=lambda _node: {"owner": owner, "repo": repo},
        **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
    )


def fetch_repo_issues_since_graphql(
    client: GitHubClient,
    owner: str,
    repo: str,
    since: datetime,
    states: list[str] | None = None,
) -> list[IssueRecord]:
    """Fetch issues for a repository updated at/after ``since`` (an incremental delta).

    Never cached — deltas change every run.
    """
    query = load_query("issues_since")
    norm_states = [s.upper() for s in states] if states else None
    return fetch_github_resource(
        client,
        query,
        {"owner": owner, "repo": repo, "states": norm_states, "since": since.isoformat()},
        IssueRecord,
        ["repository", "issues"],
        cache_key="repo_issues_since",
        cache_scope=f"{owner}_{repo}",
        cache_parameters={"owner": owner, "repo": repo, "since": since.isoformat()},
        context_builder=lambda _node: {"owner": owner, "repo": repo},
        use_cache=False,
    )


def fetch_org_issues_graphql(
    client: GitHubClient,
    org: str,
    states: list[str] | None = None,
    max_workers: int = GITHUB_MAX_WORKERS,
    *,
    refresh: bool = False,
) -> list[IssueRecord]:
    """Fetch all org issues incrementally via the persistent dataset store.

    The first run does a full fetch; later runs fetch only issues updated since
    the stored watermark and merge them in. The since-fetch falls back to a full
    fetch on any error, so this is never slower or more broken than a full fetch.
    ``refresh=True`` forces a full re-fetch (self-heal).
    """
    norm_states = sorted(s.upper() for s in states) if states else []
    fingerprint = "-".join(norm_states) if norm_states else "all"

    def full_fetch() -> list[IssueRecord]:
        return _fetch_org_records_parallel(
            client,
            org,
            max_workers,
            lambda repo: fetch_repo_issues_graphql(client, repo.owner, repo.name, states=states, use_cache=False),
            "organization issues",
        )

    def since_fetch(since: datetime) -> list[IssueRecord]:
        try:
            return _fetch_org_records_parallel(
                client,
                org,
                max_workers,
                lambda repo: fetch_repo_issues_since_graphql(client, repo.owner, repo.name, since, states),
                "organization issue updates",
            )
        except PartialOrgFetchError:
            raise  # let the store hold the watermark; don't fall back to full
        except Exception:
            logger.exception("Incremental issue fetch failed; falling back to full fetch")
            return full_fetch()

    return fetch_incremental(
        path=dataset_path("issues", org, fingerprint),
        model_class=IssueRecord,
        key_of=lambda record: (record.repo, record.number),
        updated_at_of=lambda record: record.updated_at,
        full_fetch=full_fetch,
        since_fetch=since_fetch,
        force_full=refresh,
        full_refresh_after=timedelta(days=30),
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
    transfers a fraction of the data and avoids the REST endpoint's 300-page cap,
    and is cached on a stable key (owner/repo/states) rather than a per-run
    ``since`` timestamp. The nested ``timelineItems`` connection is capped at 100
    events per issue (no inner pagination); ``from_github_node`` logs a warning on
    the rare issue that exceeds it.
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


def fetch_repo_issue_label_events_since_graphql(
    client: GitHubClient,
    owner: str,
    repo: str,
    since: datetime,
    states: list[str] | None = None,
) -> list[IssueTimelineEventRecord]:
    """Fetch label events for issues updated at/after ``since`` (an incremental delta).

    Never cached — deltas change every run.
    """
    query = load_query("issue_label_events_since")
    norm_states = [s.upper() for s in states] if states else None
    return fetch_github_resource(
        client,
        query,
        {"owner": owner, "repo": repo, "states": norm_states, "since": since.isoformat()},
        IssueTimelineEventRecord,
        ["repository", "issues"],
        cache_key="repo_issue_label_events_since",
        cache_scope=f"{owner}_{repo}",
        cache_parameters={"owner": owner, "repo": repo, "since": since.isoformat()},
        context_builder=lambda _node: {"owner": owner, "repo": repo},
        use_cache=False,
    )


def fetch_org_issue_label_events_graphql(
    client: GitHubClient,
    org: str,
    states: list[str] | None = None,
    max_workers: int = GITHUB_MAX_WORKERS,
    *,
    refresh: bool = False,
) -> list[IssueTimelineEventRecord]:
    """Fetch org issue label events incrementally via the persistent dataset store.

    Label events are immutable, and any label change bumps the issue's
    ``updatedAt``, so an issues ``filterBy: {since}`` query never misses a new
    event. The first run is a full fetch; later runs fetch only events on issues
    changed since the watermark and merge them in (deduped by event identity).
    The since-fetch falls back to a full fetch on error. ``refresh=True`` forces
    a full re-fetch.
    """
    norm_states = sorted(s.upper() for s in states) if states else []
    fingerprint = "-".join(norm_states) if norm_states else "all"

    def full_fetch() -> list[IssueTimelineEventRecord]:
        return _fetch_org_records_parallel(
            client,
            org,
            max_workers,
            lambda repo: fetch_repo_issue_label_events_graphql(
                client, repo.owner, repo.name, states=states, use_cache=False
            ),
            "organization issue label events",
        )

    def since_fetch(since: datetime) -> list[IssueTimelineEventRecord]:
        try:
            return _fetch_org_records_parallel(
                client,
                org,
                max_workers,
                lambda repo: fetch_repo_issue_label_events_since_graphql(client, repo.owner, repo.name, since, states),
                "organization issue label event updates",
            )
        except PartialOrgFetchError:
            raise  # let the store hold the watermark; don't fall back to full
        except Exception:
            logger.exception("Incremental label-event fetch failed; falling back to full fetch")
            return full_fetch()

    return fetch_incremental(
        path=dataset_path("issue_label_events", org, fingerprint),
        model_class=IssueTimelineEventRecord,
        key_of=lambda e: (e.repo, e.issue_number, e.event_type, e.occurred_at, e.label),
        updated_at_of=lambda e: e.occurred_at,
        full_fetch=full_fetch,
        since_fetch=since_fetch,
        force_full=refresh,
        full_refresh_after=timedelta(days=30),
    )
