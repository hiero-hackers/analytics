"""Tests for file-backed GitHub data source caching."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest

import hiero_analytics.data_sources.cache as cache
import hiero_analytics.data_sources.github_ingest as ingest
from hiero_analytics.data_sources.models import (
    ContributorActivityRecord,
    IssueRecord,
    IssueTimelineEventRecord,
    RepositoryRecord,
)


@pytest.fixture(name="_temp_cache_dir")
def fixture_temp_cache_dir(monkeypatch, tmp_path):
    """Point cache writes at a temporary directory for test isolation."""
    monkeypatch.setattr(cache, "GITHUB_CACHE_DIR", tmp_path / "github")
    return cache.GITHUB_CACHE_DIR


def test_issue_record_cache_round_trip(_temp_cache_dir):
    """Cached issue records should deserialize back to the original values."""
    records = [
        IssueRecord(
            repo="org/repo",
            number=1,
            title="Issue A",
            state="OPEN",
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
            closed_at=None,
            labels=["bug"],
        )
    ]
    parameters = {
        "owner": "org",
        "repo": "repo",
        "states": ["OPEN"],
    }

    cache.save_records_cache(
        "repo_issues",
        "org_repo",
        parameters,
        IssueRecord,
        records,
        use_cache=True,
    )

    loaded = cache.load_records_cache(
        "repo_issues",
        "org_repo",
        parameters,
        IssueRecord,
        use_cache=True,
        ttl_seconds=60,
    )

    assert loaded == records


def test_repository_record_cache_round_trip(_temp_cache_dir):
    """Both datetime fields on a repository record must survive a cache round-trip."""
    records = [
        RepositoryRecord(
            full_name="org/repo",
            name="repo",
            owner="org",
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
            pushed_at=datetime(2024, 6, 1, tzinfo=UTC),
            language="Python",
        )
    ]
    parameters = {"org": "org"}

    cache.save_records_cache(
        "org_repos",
        "org",
        parameters,
        RepositoryRecord,
        records,
        use_cache=True,
    )

    loaded = cache.load_records_cache(
        "org_repos",
        "org",
        parameters,
        RepositoryRecord,
        use_cache=True,
        ttl_seconds=60,
    )

    assert loaded == records
    # Guards against the registry regression: pushed_at must be a datetime, not a str.
    assert isinstance(loaded[0].pushed_at, datetime)


def test_contributor_activity_record_cache_round_trip(_temp_cache_dir):
    """Cached contributor activity records should deserialize back correctly."""
    records = [
        ContributorActivityRecord(
            repo="org/repo",
            activity_type="reviewed_pull_request",
            actor="alice",
            occurred_at=datetime(2024, 1, 2, tzinfo=UTC),
            target_type="pull_request",
            target_number=10,
            target_author="bob",
            detail="APPROVED",
        )
    ]
    parameters = {
        "owner": "org",
        "repo": "repo",
        "lookback_days": 30,
    }

    cache.save_records_cache(
        "repo_contributor_activity",
        "org_repo",
        parameters,
        ContributorActivityRecord,
        records,
        use_cache=True,
    )

    loaded = cache.load_records_cache(
        "repo_contributor_activity",
        "org_repo",
        parameters,
        ContributorActivityRecord,
        use_cache=True,
        ttl_seconds=60,
    )

    assert loaded == records


def test_issue_timeline_event_record_cache_round_trip(_temp_cache_dir):
    """Cached issue timeline events should deserialize back correctly."""
    records = [
        IssueTimelineEventRecord(
            repo="org/repo",
            issue_number=10,
            event_type="labeled",
            occurred_at=datetime(2024, 1, 2, tzinfo=UTC),
            label="good first issue",
        )
    ]
    parameters = {
        "owner": "org",
        "repo": "repo",
        "issue_number": 10,
    }

    cache.save_records_cache(
        "repo_issue_timeline_events",
        "org_repo_10",
        parameters,
        IssueTimelineEventRecord,
        records,
        use_cache=True,
    )

    loaded = cache.load_records_cache(
        "repo_issue_timeline_events",
        "org_repo_10",
        parameters,
        IssueTimelineEventRecord,
        use_cache=True,
        ttl_seconds=60,
    )

    assert loaded == records


def test_stale_cache_entry_is_ignored(_temp_cache_dir):
    """Expired cache entries should be treated as misses."""
    records = [
        IssueRecord(
            repo="org/repo",
            number=1,
            title="Issue A",
            state="OPEN",
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
            closed_at=None,
            labels=["bug"],
        )
    ]
    parameters = {"owner": "org", "repo": "repo", "states": []}

    cache.save_records_cache(
        "repo_issues",
        "org_repo",
        parameters,
        IssueRecord,
        records,
        use_cache=True,
    )

    cache_path = cache._cache_path("repo_issues", "org_repo", parameters)
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    payload["cached_at"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    cache_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = cache.load_records_cache(
        "repo_issues",
        "org_repo",
        parameters,
        IssueRecord,
        use_cache=True,
        ttl_seconds=60,
    )

    assert loaded is None


def test_naive_cached_at_is_treated_as_utc(_temp_cache_dir):
    """Naive cache timestamps should be normalized to UTC instead of failing."""
    records = [
        IssueRecord(
            repo="org/repo",
            number=1,
            title="Issue A",
            state="OPEN",
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
            closed_at=None,
            labels=["bug"],
        )
    ]
    parameters = {"owner": "org", "repo": "repo", "states": []}

    cache.save_records_cache(
        "repo_issues",
        "org_repo",
        parameters,
        IssueRecord,
        records,
        use_cache=True,
    )

    cache_path = cache._cache_path("repo_issues", "org_repo", parameters)
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    payload["cached_at"] = datetime.now(UTC).replace(tzinfo=None).isoformat()
    cache_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = cache.load_records_cache(
        "repo_issues",
        "org_repo",
        parameters,
        IssueRecord,
        use_cache=True,
        ttl_seconds=60,
    )

    assert loaded == records


def test_fetch_repo_issues_graphql_uses_cache(monkeypatch, _temp_cache_dir):
    """A second repo-issues fetch should reuse cached normalized records."""
    mock_client = Mock()

    monkeypatch.setattr(
        ingest,
        "paginate_cursor",
        lambda fetch_page: fetch_page(None)[0],
    )

    mock_client.graphql.return_value = {
        "data": {
            "repository": {
                "issues": {
                    "nodes": [
                        {
                            "number": 1,
                            "title": "Issue A",
                            "state": "OPEN",
                            "createdAt": "2024-01-01T00:00:00Z",
                            "closedAt": None,
                            "labels": {"nodes": [{"name": "bug"}]},
                        }
                    ],
                    "pageInfo": {
                        "hasNextPage": False,
                        "endCursor": None,
                    },
                }
            }
        }
    }

    first = ingest.fetch_repo_issues_graphql(
        mock_client,
        "org",
        "repo",
        use_cache=True,
        cache_ttl_seconds=300,
    )

    mock_client.graphql.reset_mock()

    second = ingest.fetch_repo_issues_graphql(
        mock_client,
        "org",
        "repo",
        use_cache=True,
        cache_ttl_seconds=300,
    )

    mock_client.graphql.assert_not_called()
    assert second == first


def test_fetch_org_issues_graphql_uses_cached_dataset(monkeypatch, _temp_cache_dir):
    """An org-level cache hit should skip nested repo fetches entirely."""
    mock_client = Mock()
    repos = [Mock(owner="org", name="repo", full_name="org/repo")]
    issues = [
        IssueRecord(
            repo="org/repo",
            number=1,
            title="Issue A",
            state="OPEN",
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
            closed_at=None,
            labels=["bug"],
        )
    ]

    fetch_org_repos = Mock(return_value=repos)
    fetch_repo_issues = Mock(return_value=issues)
    monkeypatch.setattr(ingest, "fetch_org_repos_graphql", fetch_org_repos)
    monkeypatch.setattr(ingest, "fetch_repo_issues_graphql", fetch_repo_issues)

    first = ingest.fetch_org_issues_graphql(
        mock_client,
        "org",
        use_cache=True,
        cache_ttl_seconds=300,
    )

    fetch_org_repos.reset_mock()
    fetch_repo_issues.reset_mock()

    second = ingest.fetch_org_issues_graphql(
        mock_client,
        "org",
        use_cache=True,
        cache_ttl_seconds=300,
    )

    fetch_org_repos.assert_not_called()
    fetch_repo_issues.assert_not_called()
    assert second == first


def test_fetch_org_issues_graphql_sorts_states_for_cache_key(monkeypatch, _temp_cache_dir):
    """Org cache entries should be reused regardless of state filter order."""
    mock_client = Mock()
    repos = [Mock(owner="org", name="repo", full_name="org/repo")]
    issues = [
        IssueRecord(
            repo="org/repo",
            number=1,
            title="Issue A",
            state="OPEN",
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
            closed_at=None,
            labels=["bug"],
        )
    ]

    fetch_org_repos = Mock(return_value=repos)
    fetch_repo_issues = Mock(return_value=issues)
    monkeypatch.setattr(ingest, "fetch_org_repos_graphql", fetch_org_repos)
    monkeypatch.setattr(ingest, "fetch_repo_issues_graphql", fetch_repo_issues)

    first = ingest.fetch_org_issues_graphql(
        mock_client,
        "org",
        states=["closed", "open"],
        use_cache=True,
        cache_ttl_seconds=300,
    )

    fetch_org_repos.reset_mock()
    fetch_repo_issues.reset_mock()

    second = ingest.fetch_org_issues_graphql(
        mock_client,
        "org",
        states=["OPEN", "CLOSED"],
        use_cache=True,
        cache_ttl_seconds=300,
    )

    fetch_org_repos.assert_not_called()
    fetch_repo_issues.assert_not_called()
    assert second == first
