"""Tests for the shared org-incremental resource skeleton and its registry."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

import hiero_analytics.config.paths as paths
from hiero_analytics.data_sources.github_ingest import ORG_INCREMENTAL_RESOURCES
from hiero_analytics.data_sources.github_ingest.incremental import (
    OrgIncrementalResource,
    fetch_org_incremental,
)
from hiero_analytics.data_sources.models import IssueTimelineEventRecord

_NOW = datetime.now(UTC)


def _event(number: int, days_ago: int) -> IssueTimelineEventRecord:
    return IssueTimelineEventRecord(
        repo="org/repo",
        issue_number=number,
        event_type="labeled",
        occurred_at=_NOW - timedelta(days=days_ago),
        label="bug",
        actor="alice",
    )


_RESOURCE = OrgIncrementalResource(
    name="test_events",
    model_class=IssueTimelineEventRecord,
    key_of=lambda event: (event.repo, event.issue_number, event.occurred_at),
    updated_at_of=lambda event: event.occurred_at,
    task_desc="test events",
)


def test_registry_lists_every_org_incremental_resource():
    """The registry is the enumerable source of truth for org-wide datasets."""
    assert set(ORG_INCREMENTAL_RESOURCES) == {
        "issues",
        "issue_label_events",
        "merged_pr_difficulty",
        "contributor_activity",
        "pr_hip_references",
    }
    for name, resource in ORG_INCREMENTAL_RESOURCES.items():
        assert resource.name == name


def test_first_run_full_then_incremental_merge(monkeypatch, tmp_path):
    """First run does a full fetch; the next fetches the delta and merges."""
    monkeypatch.setattr(paths, "DATASETS_DIR", tmp_path)
    calls: list[str] = []

    first = fetch_org_incremental(
        _RESOURCE,
        org="org",
        full_fetch=lambda: calls.append("full") or [_event(1, days_ago=10)],
        since_fetch=lambda _since: calls.append("since") or [],
    )
    assert calls == ["full"]
    assert [event.issue_number for event in first] == [1]

    second = fetch_org_incremental(
        _RESOURCE,
        org="org",
        full_fetch=lambda: calls.append("full") or [],
        since_fetch=lambda _since: calls.append("since") or [_event(2, days_ago=1)],
    )
    assert calls == ["full", "since"]
    assert {event.issue_number for event in second} == {1, 2}


def test_since_failure_falls_back_to_full(monkeypatch, tmp_path):
    """A non-partial since failure falls back to a full fetch instead of raising."""
    monkeypatch.setattr(paths, "DATASETS_DIR", tmp_path)

    fetch_org_incremental(
        _RESOURCE,
        org="org",
        full_fetch=lambda: [_event(1, days_ago=10)],
        since_fetch=lambda _since: [],
    )

    def broken_since(_since: datetime) -> list:
        raise ValueError("boom")

    result = fetch_org_incremental(
        _RESOURCE,
        org="org",
        full_fetch=lambda: [_event(3, days_ago=2)],
        since_fetch=broken_since,
    )
    # The fallback's records merge into the stored dataset (idempotent upsert),
    # so the previously fetched event survives alongside the fallback's.
    assert {event.issue_number for event in result} == {1, 3}


def test_batched_delta_styles_are_mutually_exclusive():
    """Exactly one of since_query_name / node_older_than must be provided."""
    from hiero_analytics.data_sources.github_ingest.incremental import fetch_org_batched_incremental

    with pytest.raises(ValueError, match="exactly one"):
        fetch_org_batched_incremental(
            object(),  # client is unused before validation
            _RESOURCE,
            org="org",
            query_name="q",
            nodes_path=["issues"],
            per_repo=lambda _repo: [],
            per_repo_since=lambda _repo, _since: [],
        )
