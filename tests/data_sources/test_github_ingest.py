"""Tests for GitHub ingest helpers, including issue timeline history fetches."""

from datetime import datetime
from unittest.mock import Mock

import pytest

import hiero_analytics.data_sources.github_ingest as ingest
from hiero_analytics.data_sources.models import (
    IssueRecord,
    IssueTimelineEventRecord,
    PullRequestDifficultyRecord,
    RepositoryRecord,
)

# ---------------------------------------------------------
# helpers
# ---------------------------------------------------------

@pytest.fixture
def mock_client():
    """Provide a shared mock GitHub client."""
    return Mock()


@pytest.fixture
def bypass_pagination(monkeypatch):
    """Replace paginate_cursor with a single-page execution."""
    monkeypatch.setattr(
        ingest,
        "paginate_cursor",
        lambda f: f(None)[0],
    )


# ---------------------------------------------------------
# repositories
# ---------------------------------------------------------

def test_fetch_org_repos_graphql(mock_client, bypass_pagination):
    """Org repository fetches should hydrate normalized repository records."""
    _ = bypass_pagination

    mock_client.graphql.return_value = {
        "data": {
            "organization": {
                "repositories": {
                    "nodes": [
                        {"name": "repo1"},
                        {"name": "repo2"},
                    ],
                    "pageInfo": {
                        "hasNextPage": False,
                        "endCursor": None,
                    },
                }
            }
        }
    }

    repos = ingest.fetch_org_repos_graphql(mock_client, "org")

    assert len(repos) == 2
    assert repos[0].full_name == "org/repo1"
    assert repos[1].name == "repo2"


# ---------------------------------------------------------
# repository issues
# ---------------------------------------------------------

def test_fetch_repo_issues_graphql(mock_client, bypass_pagination):
    """Repo issue fetches should hydrate normalized issue records."""
    _ = bypass_pagination

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
                            "labels": {
                                "nodes": [{"name": "bug"}],
                            },
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

    issues = ingest.fetch_repo_issues_graphql(mock_client, "org", "repo")

    assert len(issues) == 1

    issue = issues[0]

    assert isinstance(issue, IssueRecord)
    assert issue.repo == "org/repo"
    assert issue.number == 1
    assert issue.labels == ["bug"]


def test_fetch_repo_issues_normalizes_states(mock_client, bypass_pagination):
    """Repo issue fetches should normalize GraphQL state filters."""
    _ = bypass_pagination

    mock_client.graphql.return_value = {
        "data": {
            "repository": {
                "issues": {
                    "nodes": [],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }
    }

    ingest.fetch_repo_issues_graphql(
        mock_client,
        "org",
        "repo",
        states=["open"],
    )

    args, _ = mock_client.graphql.call_args

    variables = args[1]

    assert variables["states"] == ["OPEN"]


def test_fetch_repo_issue_timeline_events_rest(mock_client):
    """Timeline fetches should normalize relevant REST timeline events."""
    mock_client.get.return_value = [
        {
            "event": "labeled",
            "created_at": "2024-01-02T00:00:00Z",
            "label": {"name": "Good First Issue"},
        },
        {
            "event": "closed",
            "created_at": "2024-01-03T00:00:00Z",
        },
    ]

    records = ingest.fetch_repo_issue_timeline_events_rest(
        mock_client,
        "org",
        "repo",
        1,
        use_cache=False,
    )

    assert records == [
        IssueTimelineEventRecord(
            repo="org/repo",
            issue_number=1,
            event_type="labeled",
            occurred_at=datetime.fromisoformat("2024-01-02T00:00:00+00:00"),
            label="good first issue",
        ),
        IssueTimelineEventRecord(
            repo="org/repo",
            issue_number=1,
            event_type="closed",
            occurred_at=datetime.fromisoformat("2024-01-03T00:00:00+00:00"),
            label=None,
        ),
    ]


def test_fetch_issue_timeline_events_rest_parallel(monkeypatch, mock_client):
    """Parallel issue timeline fetches should aggregate records across issues."""
    issues = [
        IssueRecord(
            repo="org/repo1",
            number=1,
            title="Issue A",
            state="OPEN",
            created_at=datetime.fromisoformat("2024-01-01T00:00:00+00:00"),
            closed_at=None,
            labels=[],
        ),
        IssueRecord(
            repo="org/repo2",
            number=2,
            title="Issue B",
            state="OPEN",
            created_at=datetime.fromisoformat("2024-01-01T00:00:00+00:00"),
            closed_at=None,
            labels=[],
        ),
    ]

    monkeypatch.setattr(
        ingest,
        "fetch_repo_issue_timeline_events_rest",
        lambda _client, owner, repo, issue_number, **_kwargs: [
            IssueTimelineEventRecord(
                repo=f"{owner}/{repo}",
                issue_number=issue_number,
                event_type="labeled",
                occurred_at=datetime.fromisoformat("2024-01-02T00:00:00+00:00"),
                label="good first issue",
            )
        ],
    )

    records = ingest.fetch_issue_timeline_events_rest(
        mock_client,
        issues,
        max_workers=2,
        use_cache=False,
    )

    assert len(records) == 2
    assert {record.repo for record in records} == {"org/repo1", "org/repo2"}


def test_fetch_repo_issue_events_rest_since(mock_client):
    """Repository issue event fetches should stop once events are older than the cutoff."""
    mock_client.get.side_effect = [
        [
            {
                "event": "labeled",
                "created_at": "2025-06-01T00:00:00Z",
                "issue": {"number": 1},
                "label": {"name": "Beginner"},
            },
            {
                "event": "closed",
                "created_at": "2025-04-01T00:00:00Z",
                "issue": {"number": 2},
            },
        ]
    ]

    records = ingest.fetch_repo_issue_events_rest_since(
        mock_client,
        "org",
        "repo",
        since=datetime.fromisoformat("2025-04-11T00:00:00+00:00"),
        use_cache=False,
    )

    assert records == [
        IssueTimelineEventRecord(
            repo="org/repo",
            issue_number=1,
            event_type="labeled",
            occurred_at=datetime.fromisoformat("2025-06-01T00:00:00+00:00"),
            label="beginner",
        )
    ]


# ---------------------------------------------------------
# org issues parallel
# ---------------------------------------------------------

def test_fetch_org_issues_graphql_parallel(monkeypatch, mock_client):
    """Org issue fetches should combine repo-level issue results."""
    repos = [
        RepositoryRecord("org/repo1", "repo1", "org"),
        RepositoryRecord("org/repo2", "repo2", "org"),
    ]

    monkeypatch.setattr(
        ingest,
        "fetch_org_repos_graphql",
        lambda _client, _org: repos,
    )

    def fetch_repo_issues(_client, owner, repo, states=None):
        _ = states
        return [
            IssueRecord(
                repo=f"{owner}/{repo}",
                number=1,
                title="Issue",
                state="OPEN",
                created_at=None,
                closed_at=None,
                labels=[],
            )
        ]

    monkeypatch.setattr(
        ingest,
        "fetch_repo_issues_graphql",
        fetch_repo_issues,
    )

    issues = ingest.fetch_org_issues_graphql(mock_client, "org", max_workers=2)

    repos_returned = {i.repo for i in issues}

    assert repos_returned == {"org/repo1", "org/repo2"}
    assert len(issues) == 2


# ---------------------------------------------------------
# merged PR difficulty
# ---------------------------------------------------------

def test_fetch_repo_merged_pr_difficulty_graphql(mock_client, bypass_pagination):
    """Merged PR difficulty fetches should hydrate linked issue records."""
    _ = bypass_pagination

    mock_client.graphql.return_value = {
        "data": {
            "repository": {
                "pullRequests": {
                    "nodes": [
                        {
                            "number": 10,
                            "createdAt": "2024-01-01T00:00:00Z",
                            "mergedAt": "2024-01-02T00:00:00Z",
                            "additions": 5,
                            "deletions": 3,
                            "changedFiles": 2,
                            "closingIssuesReferences": {
                                "nodes": [
                                    {
                                        "number": 1,
                                        "labels": {
                                            "nodes": [{"name": "good first issue"}]
                                        },
                                    }
                                ]
                            },
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

    records = ingest.fetch_repo_merged_pr_difficulty_graphql(
        mock_client,
        "org",
        "repo",
    )

    assert len(records) == 1

    record = records[0]

    assert isinstance(record, PullRequestDifficultyRecord)
    assert record.repo == "org/repo"
    assert record.pr_number == 10
    assert record.issue_number == 1


# ---------------------------------------------------------
# merged PR org parallel
# ---------------------------------------------------------

def test_fetch_org_merged_pr_difficulty_graphql(monkeypatch, mock_client):
    """Org merged-PR difficulty fetches should combine repo-level results."""
    repos = [
        RepositoryRecord("org/repo1", "repo1", "org"),
        RepositoryRecord("org/repo2", "repo2", "org"),
    ]

    monkeypatch.setattr(
        ingest,
        "fetch_org_repos_graphql",
        lambda _client, _org: repos,
    )

    monkeypatch.setattr(
        ingest,
        "fetch_repo_merged_pr_difficulty_graphql",
        lambda _client, owner, repo: [
            PullRequestDifficultyRecord(
                repo=f"{owner}/{repo}",
                pr_number=1,
                pr_created_at=None,
                pr_merged_at=None,
                pr_additions=1,
                pr_deletions=1,
                pr_changed_files=1,
                issue_number=1,
                issue_labels=[],
            )
        ],
    )

    records = ingest.fetch_org_merged_pr_difficulty_graphql(
        mock_client,
        "org",
        max_workers=2,
    )

    repos_returned = {r.repo for r in records}

    assert repos_returned == {"org/repo1", "org/repo2"}
    assert len(records) == 2


# ---------------------------------------------------------
# issue label events (GraphQL timelineItems)
# ---------------------------------------------------------

def _label_events_payload():
    """Build a GraphQL issues+timelineItems response for two issues."""
    return {
        "data": {
            "repository": {
                "issues": {
                    "nodes": [
                        {
                            "number": 1,
                            "timelineItems": {
                                "nodes": [
                                    {
                                        "__typename": "LabeledEvent",
                                        "createdAt": "2026-05-10T00:00:00Z",
                                        "label": {"name": "Beginner"},
                                    },
                                    {
                                        "__typename": "UnlabeledEvent",
                                        "createdAt": "2026-05-12T00:00:00Z",
                                        "label": {"name": "Beginner"},
                                    },
                                ]
                            },
                        },
                        {"number": 2, "timelineItems": {"nodes": []}},
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }
    }


def test_fetch_repo_issue_label_events_graphql_parses_events(mock_client, bypass_pagination):
    """The GraphQL fetch expands timelineItems into normalized label events."""
    _ = bypass_pagination
    mock_client.graphql.return_value = _label_events_payload()

    events = ingest.fetch_repo_issue_label_events_graphql(
        mock_client, "org", "repo", states=["OPEN"], use_cache=False,
    )

    assert [(e.issue_number, e.event_type, e.label) for e in events] == [
        (1, "labeled", "beginner"),
        (1, "unlabeled", "beginner"),
    ]
    assert all(e.repo == "org/repo" for e in events)


def test_fetch_repo_issue_label_events_graphql_uses_stable_cache_key(
    mock_client, bypass_pagination, monkeypatch,
):
    """Cache key must not embed a per-run timestamp (guards the since-churn bug)."""
    _ = bypass_pagination
    mock_client.graphql.return_value = _label_events_payload()

    captured: dict[str, object] = {}

    def fake_load(kind, scope, parameters, _record_type, **_kwargs):
        captured["kind"] = kind
        captured["scope"] = scope
        captured["parameters"] = parameters  # cache miss -> implicit return None

    monkeypatch.setattr(ingest, "load_records_cache", fake_load)
    monkeypatch.setattr(ingest, "save_records_cache", lambda *_a, **_k: None)

    ingest.fetch_repo_issue_label_events_graphql(mock_client, "org", "repo", states=["OPEN"])

    assert captured["scope"] == "org_repo"
    assert captured["parameters"] == {"owner": "org", "repo": "repo", "states": ["OPEN"]}
    # No volatile time component anywhere in the key.
    assert "since" not in captured["parameters"]
