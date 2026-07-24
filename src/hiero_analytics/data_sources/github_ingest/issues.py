"""Issue ingestion via the GraphQL API.

Repo- and org-level issue fetching plus issue label add/remove events. The
org-level fetchers are incremental: the persistent dataset store keeps the full
history and later runs fetch only the delta since the watermark.
"""

from __future__ import annotations

from datetime import datetime

from hiero_analytics.config.github import GITHUB_MAX_WORKERS
from hiero_analytics.data_sources.queries import load_query

from ..github_client import GitHubClient
from ..models import IssueRecord, IssueTimelineEventRecord
from ._common import (
    _cache_kwargs,
    fetch_github_resource,
)
from .incremental import OrgIncrementalResource, fetch_org_batched_incremental

ISSUES_RESOURCE = OrgIncrementalResource(
    name="issues",
    model_class=IssueRecord,
    key_of=lambda record: (record.repo, record.number),
    updated_at_of=lambda record: record.updated_at,
    task_desc="issues",
)

ISSUE_LABEL_EVENTS_RESOURCE = OrgIncrementalResource(
    name="issue_label_events",
    model_class=IssueTimelineEventRecord,
    # Events are immutable, so identity is the full event tuple and the
    # watermark advances on the event time itself.
    key_of=lambda event: (event.repo, event.issue_number, event.event_type, event.occurred_at, event.label),
    updated_at_of=lambda event: event.occurred_at,
    task_desc="issue label events",
)


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
    return fetch_org_batched_incremental(
        client,
        ISSUES_RESOURCE,
        org=org,
        query_name="issues",
        since_query_name="issues_since",
        nodes_path=["issues"],
        variables={"states": norm_states or None},
        per_repo=lambda repo: fetch_repo_issues_graphql(client, repo.owner, repo.name, states=states, use_cache=False),
        per_repo_since=lambda repo, since: fetch_repo_issues_since_graphql(
            client, repo.owner, repo.name, since, states
        ),
        fingerprint="-".join(norm_states) if norm_states else "all",
        max_workers=max_workers,
        refresh=refresh,
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
    return fetch_org_batched_incremental(
        client,
        ISSUE_LABEL_EVENTS_RESOURCE,
        org=org,
        query_name="issue_label_events",
        since_query_name="issue_label_events_since",
        nodes_path=["issues"],
        variables={"states": norm_states or None},
        per_repo=lambda repo: fetch_repo_issue_label_events_graphql(
            client, repo.owner, repo.name, states=states, use_cache=False
        ),
        per_repo_since=lambda repo, since: fetch_repo_issue_label_events_since_graphql(
            client, repo.owner, repo.name, since, states
        ),
        fingerprint="-".join(norm_states) if norm_states else "all",
        max_workers=max_workers,
        refresh=refresh,
    )
