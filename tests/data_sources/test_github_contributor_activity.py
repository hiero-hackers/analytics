"""Tests for GitHub contributor activity ingestion."""
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest

import hiero_analytics.data_sources.github_ingest as ingest
from hiero_analytics.data_sources.models import ContributorActivityRecord, RepositoryRecord


@pytest.fixture
def mock_client():
    """Mock GitHub client fixture."""
    return Mock()


@pytest.fixture
def bypass_pagination(monkeypatch):
    """Bypass pagination to return a single page."""
    monkeypatch.setattr(
        ingest,
        "paginate_cursor",
        lambda f: f(None)[0],
    )


def _to_iso(value: datetime) -> str:
    """Format a datetime as a GitHub-style ISO 8601 string."""
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def test_fetch_repo_contributor_activity_graphql(mock_client, bypass_pagination):
    """Test fetching repository contributor activity."""
    now = datetime.now(UTC)
    issue_created_at = _to_iso(now - timedelta(days=6))
    created_at = _to_iso(now - timedelta(days=5))
    reviewed_at = _to_iso(now - timedelta(days=4))
    merged_at = _to_iso(now - timedelta(days=3))

    mock_client.graphql.side_effect = [
        {
            "data": {
                "repository": {
                    "pullRequests": {
                        "nodes": [
                            {
                                "number": 10,
                                "createdAt": created_at,
                                "updatedAt": merged_at,
                                "mergedAt": merged_at,
                                "author": {"login": "alice"},
                                "mergedBy": {"login": "carol"},
                                "reviews": {
                                    "nodes": [
                                        {
                                            "state": "APPROVED",
                                            "submittedAt": reviewed_at,
                                            "author": {"login": "bob"},
                                        }
                                    ]
                                },
                            }
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        },
        {
            "data": {
                "repository": {
                    "issues": {
                        "nodes": [
                            {
                                "number": 20,
                                "createdAt": issue_created_at,
                                "author": {"login": "dana"},
                            }
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        },
    ]

    records = ingest.fetch_repo_contributor_activity_graphql(
        mock_client,
        "org",
        "repo",
        lookback_days=30,
        use_cache=False,
    )

    assert len(records) == 4
    assert all(isinstance(record, ContributorActivityRecord) for record in records)
    assert {record.activity_type for record in records} == {
        "authored_issue",
        "authored_pull_request",
        "reviewed_pull_request",
        "merged_pull_request",
    }
    issue_record = next(record for record in records if record.activity_type == "authored_issue")
    assert issue_record.actor == "dana"
    assert issue_record.target_type == "issue"
    assert issue_record.target_number == 20
    assert "states:[OPEN, CLOSED]" in mock_client.graphql.call_args_list[1].args[0]


def test_fetch_repo_issue_activity_graphql_stops_after_older_issue(mock_client):
    """Test early stop for older issues in pagination."""
    now = datetime.now(UTC)
    recent_issue_created_at = _to_iso(now - timedelta(days=5))
    older_issue_created_at = _to_iso(now - timedelta(days=40))

    mock_client.graphql.return_value = {
        "data": {
            "repository": {
                "issues": {
                    "nodes": [
                        {
                            "number": 20,
                            "createdAt": recent_issue_created_at,
                            "author": {"login": "dana"},
                        },
                        {
                            "number": 21,
                            "createdAt": older_issue_created_at,
                            "author": {"login": "erin"},
                        },
                    ],
                    "pageInfo": {"hasNextPage": True, "endCursor": "next-page"},
                }
            }
        }
    }

    records = ingest._fetch_repo_issue_activity_graphql(
        mock_client,
        "org",
        "repo",
        cutoff=now - timedelta(days=30),
    )

    assert len(records) == 1
    assert records[0].activity_type == "authored_issue"
    assert records[0].actor == "dana"
    assert mock_client.graphql.call_count == 1


def test_lookback_days_none_includes_old_activity(mock_client, bypass_pagination):
    """When lookback_days is None all historical records should be returned."""
    old_date = _to_iso(datetime(2023, 1, 15, tzinfo=UTC))

    pr_response = {
        "data": {
            "repository": {
                "pullRequests": {
                    "nodes": [
                        {
                            "number": 1,
                            "createdAt": old_date,
                            "updatedAt": old_date,
                            "mergedAt": old_date,
                            "author": {"login": "alice"},
                            "mergedBy": {"login": "bob"},
                            "reviews": {"nodes": []},
                        }
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }
    }
    empty_issues_response = {
        "data": {
            "repository": {
                "issues": {
                    "nodes": [],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }
    }

    # Each fetch_repo call triggers two GraphQL calls (PRs + issues).
    mock_client.graphql.side_effect = [
        pr_response, empty_issues_response,  # lookback_days=30
        pr_response, empty_issues_response,  # lookback_days=None
    ]

    # With a short lookback the old PR should be filtered out
    records_limited = ingest.fetch_repo_contributor_activity_graphql(
        mock_client, "org", "repo", lookback_days=30, use_cache=False,
    )
    assert len(records_limited) == 0

    # With lookback_days=None all history is included
    records_all = ingest.fetch_repo_contributor_activity_graphql(
        mock_client, "org", "repo", lookback_days=None, use_cache=False,
    )
    assert len(records_all) == 2  # authored + merged
    assert {r.activity_type for r in records_all} == {
        "authored_pull_request",
        "merged_pull_request",
    }

def test_fetch_org_contributor_activity_graphql(monkeypatch, mock_client):
    """Test fetching organization contributor activity."""
    repos = [
        RepositoryRecord("org/repo1", "repo1", "org"),
        RepositoryRecord("org/repo2", "repo2", "org"),
    ]

    monkeypatch.setattr(
        ingest,
        "fetch_org_repos_graphql",
        lambda client, org, **kwargs: repos,
    )

    monkeypatch.setattr(
        ingest,
        "fetch_repo_contributor_activity_graphql",
        lambda client, owner, repo, **kwargs: [
            ContributorActivityRecord(
                repo=f"{owner}/{repo}",
                activity_type="authored_pull_request",
                actor="alice",
                occurred_at=datetime.now(UTC),
                target_type="pull_request",
                target_number=1,
            )
        ],
    )

    records = ingest.fetch_org_contributor_activity_graphql(
        mock_client,
        "org",
        max_workers=2,
        use_cache=False,
    )

    assert len(records) == 2
    assert {record.repo for record in records} == {"org/repo1", "org/repo2"}
