"""Shared scaffolding for pipeline entry points.

Pipelines open with the same preamble — a GitHub client plus ensured output
directories — and several reuse the same persisted org-wide datasets. These
helpers keep that boilerplate (and the dataset names) in one place.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple

from hiero_analytics.config.paths import ensure_org_dirs, ensure_repo_dirs
from hiero_analytics.data_sources.dataset_store import load_or_fetch
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import (
    CONTRIBUTOR_ACTIVITY_RESOURCE,
    ISSUE_LABEL_EVENTS_RESOURCE,
    fetch_org_contributor_activity_graphql,
    fetch_org_issue_label_events_graphql,
)
from hiero_analytics.data_sources.models import ContributorActivityRecord, IssueTimelineEventRecord
from hiero_analytics.data_sources.usage import UsageLedger


class PipelineContext(NamedTuple):
    """The standard pipeline preamble: an API client plus the ensured output dir."""

    client: GitHubClient
    data_dir: Path


_client: GitHubClient | None = None


def shared_client() -> GitHubClient:
    """The process-wide GitHub client, created on first use.

    Rate-limit backoff is already process-wide (the client module's shared
    limiter); sharing one client additionally gives every pipeline in a run
    the same HTTP session and connection pool.
    """
    global _client
    if _client is None:
        _client = GitHubClient()
    return _client


def api_usage_summary() -> dict[str, Any]:
    """The run's GitHub API usage so far, as a JSON-ready dict.

    All zeros when no client was ever created (an offline run, say) — asking
    must not construct a client, which would log a missing-token warning for a
    run that never needed one.
    """
    ledger = _client.usage if _client is not None else UsageLedger()
    return ledger.summary()


def reset_api_usage() -> None:
    """Start a fresh usage count; a no-op until a client exists."""
    if _client is not None:
        _client.usage.reset()


def org_context(org: str) -> PipelineContext:
    """Shared client plus the org's ensured data output directory."""
    return PipelineContext(shared_client(), ensure_org_dirs(org))


def repo_context(org: str, repo: str) -> PipelineContext:
    """Shared client plus the repo's ensured data output directory."""
    return PipelineContext(shared_client(), ensure_repo_dirs(f"{org}/{repo}"))


def load_contributor_activity(client: GitHubClient, org: str) -> list[ContributorActivityRecord]:
    """The persisted org-wide contributor-activity dataset, fetched on a cold start.

    Shared across pipelines within a run: whichever pipeline needs it first
    fetches and persists it; the rest read it from disk.
    """
    # Name and schema come from the resource that writes the file, so a schema
    # bump there cannot leave this reader missing on every call.
    return load_or_fetch(
        CONTRIBUTOR_ACTIVITY_RESOURCE.name,
        org,
        ContributorActivityRecord,
        lambda: fetch_org_contributor_activity_graphql(client, org=org, lookback_days=None),
        schema_version=CONTRIBUTOR_ACTIVITY_RESOURCE.schema_version,
    )


def load_issue_label_events(
    client: GitHubClient,
    org: str,
    *,
    max_workers: int | None = None,
) -> list[IssueTimelineEventRecord]:
    """The persisted org-wide issue label-event dataset, fetched on a cold start.

    Shared across pipelines within a run: whichever pipeline needs it first
    fetches and persists it; the rest read it from disk. Every caller reads the
    *same* all-states dataset (``fingerprint="all"``), so customizing to open
    issues only is the caller's own issue-set join, not a separate fetch.

    ``max_workers`` throttles the underlying fetch and only has an effect on the
    run that triggers the cold fetch — pass ``TIMELINE_MAX_WORKERS`` from the
    event-heavy pipelines.
    """
    kwargs = {} if max_workers is None else {"max_workers": max_workers}
    return load_or_fetch(
        ISSUE_LABEL_EVENTS_RESOURCE.name,
        org,
        IssueTimelineEventRecord,
        lambda: fetch_org_issue_label_events_graphql(client, org=org, **kwargs),
        schema_version=ISSUE_LABEL_EVENTS_RESOURCE.schema_version,
    )
