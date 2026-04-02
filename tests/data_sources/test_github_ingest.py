from datetime import datetime
from unittest.mock import Mock

import pytest

import hiero_analytics.data_sources.github_ingest as ingest
from hiero_analytics.data_sources.models import (
    IssueRecord,
    PullRequestDifficultyRecord,
    RepositoryRecord,
)

# ---------------------------------------------------------
# helpers
# ---------------------------------------------------------

@pytest.fixture
def mock_client():
    return Mock()


@pytest.fixture
def bypass_pagination(monkeypatch):
    """
    Replace paginate_cursor with a single-page execution.
    """
    monkeypatch.setattr(
        ingest,
        "paginate_cursor",
        lambda f: f(None)[0],
    )


# ---------------------------------------------------------
# repositories
# ---------------------------------------------------------

def test_fetch_org_repos_graphql(mock_client, bypass_pagination):

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


# ---------------------------------------------------------
# org issues parallel
# ---------------------------------------------------------

def test_fetch_org_issues_graphql_parallel(monkeypatch, mock_client):

    repos = [
        RepositoryRecord("org/repo1", "repo1", "org"),
        RepositoryRecord("org/repo2", "repo2", "org"),
    ]

    monkeypatch.setattr(
        ingest,
        "fetch_org_repos_graphql",
        lambda client, org: repos,
    )

    monkeypatch.setattr(
        ingest,
        "fetch_repo_issues_graphql",
        lambda client, owner, repo, states=None: [
            IssueRecord(
                repo=f"{owner}/{repo}",
                number=1,
                title="Issue",
                state="OPEN",
                created_at=None,
                closed_at=None,
                labels=[],
            )
        ],
    )

    issues = ingest.fetch_org_issues_graphql(mock_client, "org", max_workers=2)

    repos_returned = {i.repo for i in issues}

    assert repos_returned == {"org/repo1", "org/repo2"}
    assert len(issues) == 2


# ---------------------------------------------------------
# merged PR difficulty
# ---------------------------------------------------------

def test_fetch_repo_merged_pr_difficulty_graphql(mock_client, bypass_pagination):

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

    repos = [
        RepositoryRecord("org/repo1", "repo1", "org"),
        RepositoryRecord("org/repo2", "repo2", "org"),
    ]

    monkeypatch.setattr(
        ingest,
        "fetch_org_repos_graphql",
        lambda client, org: repos,
    )

    monkeypatch.setattr(
        ingest,
        "fetch_repo_merged_pr_difficulty_graphql",
        lambda client, owner, repo: [
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