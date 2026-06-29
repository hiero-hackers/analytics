"""Tests for file-backed GitHub data source caching."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest

import hiero_analytics.data_sources.cache as cache
import hiero_analytics.data_sources.github_ingest as ingest
import hiero_analytics.data_sources.serialization as serialization
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
        ingest._common,
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


def _isolate_dataset_path(monkeypatch, tmp_path):
    """Redirect the committed dataset path into a temp dir for test isolation.

    ``dataset_path`` is imported into both resource submodules that use it, so
    patch it on each (the org-issues and contributor-activity call sites).
    """
    def fake(resource, scope, fingerprint="all"):
        return tmp_path / f"{resource}_{scope}_{fingerprint}.json"

    monkeypatch.setattr(ingest.issues, "dataset_path", fake)
    monkeypatch.setattr(ingest.contributors, "dataset_path", fake)


def test_fetch_org_issues_first_run_full_then_incremental(monkeypatch, tmp_path):
    """First org-issues fetch is full; the next fetches only the delta and merges."""
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
            # Recent so the 30-day full-refresh self-heal does not trigger here;
            # this test exercises the incremental (since) path on the 2nd run.
            updated_at=datetime.now(UTC),
        )
    ]

    _isolate_dataset_path(monkeypatch, tmp_path)
    monkeypatch.setattr(ingest._common, "fetch_org_repos_graphql", Mock(return_value=repos))
    full = Mock(return_value=issues)
    delta = Mock(return_value=[])  # nothing changed since the watermark
    monkeypatch.setattr(ingest.issues, "fetch_repo_issues_graphql", full)
    monkeypatch.setattr(ingest.issues, "fetch_repo_issues_since_graphql", delta)

    first = ingest.fetch_org_issues_graphql(mock_client, "org")
    assert first == issues
    full.assert_called_once()
    delta.assert_not_called()

    full.reset_mock()
    second = ingest.fetch_org_issues_graphql(mock_client, "org")

    full.assert_not_called()      # second run does not do a full fetch
    delta.assert_called_once()    # it fetches the incremental delta
    assert second == issues       # empty delta -> merged set unchanged


def test_fetch_org_issues_dataset_fingerprint_ignores_state_order(monkeypatch, tmp_path):
    """State filter order does not change the dataset file (same fingerprint)."""
    mock_client = Mock()
    seen_paths = []

    def fake_path(resource, scope, fingerprint="all"):
        path = tmp_path / f"{resource}_{scope}_{fingerprint}.json"
        seen_paths.append(path)
        return path

    monkeypatch.setattr(ingest.issues, "dataset_path", fake_path)
    monkeypatch.setattr(ingest._common, "fetch_org_repos_graphql", Mock(return_value=[]))
    monkeypatch.setattr(ingest.issues, "fetch_repo_issues_graphql", Mock(return_value=[]))
    monkeypatch.setattr(ingest.issues, "fetch_repo_issues_since_graphql", Mock(return_value=[]))

    ingest.fetch_org_issues_graphql(mock_client, "org", states=["closed", "open"])
    ingest.fetch_org_issues_graphql(mock_client, "org", states=["OPEN", "CLOSED"])

    assert seen_paths[0] == seen_paths[1]  # identical regardless of state order


def test_fetch_org_label_events_incremental_dedups_on_merge(monkeypatch, tmp_path):
    """The 2nd run fetches the delta and merges events without double-counting."""
    mock_client = Mock()
    repos = [Mock(owner="org", name="repo", full_name="org/repo")]
    occurred = datetime.now(UTC)  # recent, so the 30-day refresh does not trigger
    ev1 = IssueTimelineEventRecord(
        repo="org/repo", issue_number=1, event_type="labeled",
        occurred_at=occurred, label="bug",
    )
    ev2 = IssueTimelineEventRecord(
        repo="org/repo", issue_number=2, event_type="unlabeled",
        occurred_at=occurred, label="bug",
    )

    _isolate_dataset_path(monkeypatch, tmp_path)
    monkeypatch.setattr(ingest._common, "fetch_org_repos_graphql", Mock(return_value=repos))
    full = Mock(return_value=[ev1])
    delta = Mock(return_value=[ev1, ev2])  # re-sends ev1 (must dedup) + a new ev2
    monkeypatch.setattr(ingest.issues, "fetch_repo_issue_label_events_graphql", full)
    monkeypatch.setattr(ingest.issues, "fetch_repo_issue_label_events_since_graphql", delta)

    first = ingest.fetch_org_issue_label_events_graphql(mock_client, "org")
    assert first == [ev1]
    full.assert_called_once()

    second = ingest.fetch_org_issue_label_events_graphql(mock_client, "org")
    delta.assert_called_once()
    keys = {(e.repo, e.issue_number, e.event_type, e.occurred_at, e.label) for e in second}
    assert len(second) == 2  # ev1 deduped (not 3), ev2 added
    assert len(keys) == 2


def test_fetch_org_contributor_activity_full_history_is_incremental(monkeypatch, tmp_path):
    """lookback_days=None routes through the dataset store: full then delta-merge."""
    mock_client = Mock()
    repos = [Mock(owner="org", name="repo", full_name="org/repo")]
    occurred = datetime.now(UTC)
    ev1 = ContributorActivityRecord(
        repo="org/repo", activity_type="authored_pull_request", actor="alice",
        occurred_at=occurred, target_type="pull_request", target_number=1,
    )
    ev2 = ContributorActivityRecord(
        repo="org/repo", activity_type="reviewed_pull_request", actor="bob",
        occurred_at=occurred, target_type="pull_request", target_number=2,
    )

    _isolate_dataset_path(monkeypatch, tmp_path)
    monkeypatch.setattr(ingest._common, "fetch_org_repos_graphql", Mock(return_value=repos))

    def at_cutoff(_client, _owner, _repo, cutoff):
        return [ev1] if cutoff is None else [ev1, ev2]  # full vs delta (re-sends ev1)

    monkeypatch.setattr(ingest.contributors, "_fetch_repo_contributor_activity_at_cutoff", at_cutoff)

    first = ingest.fetch_org_contributor_activity_graphql(mock_client, "org", lookback_days=None)
    assert first == [ev1]

    second = ingest.fetch_org_contributor_activity_graphql(mock_client, "org", lookback_days=None)
    keys = {
        (e.repo, e.activity_type, e.actor, e.occurred_at, e.target_type, e.target_number)
        for e in second
    }
    assert len(second) == 2  # ev1 deduped, ev2 added
    assert len(keys) == 2


def test_fetch_org_contributor_activity_bounded_window_skips_dataset(monkeypatch):
    """lookback_days set uses the bounded path and writes no incremental dataset."""
    mock_client = Mock()

    def fake_path(*_a, **_k):
        raise AssertionError("dataset_path used for the bounded-window path")

    monkeypatch.setattr(ingest.contributors, "dataset_path", fake_path)
    monkeypatch.setattr(ingest._common, "fetch_org_repos_graphql", Mock(return_value=[]))

    result = ingest.fetch_org_contributor_activity_graphql(mock_client, "org", lookback_days=183)
    assert result == []


# ---------------------------------------------------------
# _datetime_fields derivation (registry-free datetime handling)
# ---------------------------------------------------------

def test_datetime_fields_match_each_record_schema():
    """Every record's datetime fields are derived from its type hints."""
    assert serialization.datetime_fields(RepositoryRecord) == ("created_at", "pushed_at")
    assert serialization.datetime_fields(IssueRecord) == ("created_at", "closed_at", "updated_at")
    assert serialization.datetime_fields(IssueTimelineEventRecord) == ("occurred_at",)
    assert serialization.datetime_fields(ContributorActivityRecord) == ("occurred_at",)


def test_datetime_fields_auto_discovers_new_datetime_field():
    """A new datetime field is found without touching any registry.

    This is the property the refactor guarantees: adding a datetime field to a
    record can never silently break cache round-tripping.
    """
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class _SampleRecord:
        name: str
        created_at: datetime
        deleted_at: datetime | None
        count: int

    assert serialization.datetime_fields(_SampleRecord) == ("created_at", "deleted_at")


def test_datetime_fields_empty_for_records_without_datetimes():
    """A record with no datetime fields derives an empty tuple."""
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class _PlainRecord:
        name: str
        active: bool

    assert serialization.datetime_fields(_PlainRecord) == ()
