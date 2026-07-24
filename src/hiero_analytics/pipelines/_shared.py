"""Shared scaffolding for pipeline entry points.

Pipelines open with the same preamble — a GitHub client plus ensured output
directories — and several reuse the same persisted org-wide datasets. These
helpers keep that boilerplate (and the dataset names) in one place.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from hiero_analytics.config.paths import ensure_org_dirs, ensure_repo_dirs
from hiero_analytics.data_sources.dataset_store import load_or_fetch
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import (
    fetch_org_contributor_activity_graphql,
    fetch_org_issue_label_events_graphql,
)
from hiero_analytics.data_sources.models import ContributorActivityRecord, IssueTimelineEventRecord


class PipelineContext(NamedTuple):
    """The standard pipeline preamble: an API client plus ensured output dirs."""

    client: GitHubClient
    data_dir: Path
    charts_dir: Path


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


def org_context(org: str) -> PipelineContext:
    """Shared client plus the org's ensured (data, charts) output directories."""
    data_dir, charts_dir = ensure_org_dirs(org)
    return PipelineContext(shared_client(), data_dir, charts_dir)


def repo_context(org: str, repo: str) -> PipelineContext:
    """Shared client plus the repo's ensured (data, charts) output directories."""
    data_dir, charts_dir = ensure_repo_dirs(f"{org}/{repo}")
    return PipelineContext(shared_client(), data_dir, charts_dir)


def load_contributor_activity(client: GitHubClient, org: str) -> list[ContributorActivityRecord]:
    """The persisted org-wide contributor-activity dataset, fetched on a cold start.

    Shared across pipelines within a run: whichever pipeline needs it first
    fetches and persists it; the rest read it from disk.
    """
    return load_or_fetch(
        "contributor_activity",
        org,
        ContributorActivityRecord,
        lambda: fetch_org_contributor_activity_graphql(client, org=org, lookback_days=None),
    )


def load_issue_label_events(client: GitHubClient, org: str) -> list[IssueTimelineEventRecord]:
    """The persisted org-wide issue label-event dataset, fetched on a cold start."""
    return load_or_fetch(
        "issue_label_events",
        org,
        IssueTimelineEventRecord,
        lambda: fetch_org_issue_label_events_graphql(client, org=org),
    )
