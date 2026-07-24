"""Tests for GitHub ingest helpers, including issue timeline history fetches."""

from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

import hiero_analytics.data_sources.github_ingest as ingest
from hiero_analytics.data_sources.dataset_store import PartialOrgFetchError
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
    """Provide a shared mock GitHub client."""
    return Mock()


@pytest.fixture
def bypass_pagination(monkeypatch):
    """Replace paginate_cursor with a single-page execution."""
    monkeypatch.setattr(
        ingest._common,
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


# ---------------------------------------------------------
# org issues parallel
# ---------------------------------------------------------


def test_fetch_org_issues_graphql_parallel(monkeypatch, mock_client, tmp_path):
    """A first org-issue fetch combines per-repo full-fetch results."""
    repos = [
        RepositoryRecord("org/repo1", "repo1", "org"),
        RepositoryRecord("org/repo2", "repo2", "org"),
    ]

    monkeypatch.setattr(
        ingest.incremental,
        "dataset_path",
        lambda resource, scope, fingerprint="all": tmp_path / f"{resource}_{scope}_{fingerprint}.json",
    )
    monkeypatch.setattr(
        ingest._common,
        "fetch_org_repos_graphql",
        lambda _client, _org: repos,
    )
    monkeypatch.setattr(
        ingest.incremental,
        "fetch_org_records_batched",
        lambda _client, _org, *, per_repo, **_kwargs: [record for repo in repos for record in per_repo(repo)],
    )

    def fetch_repo_issues(_client, owner, repo, **_kwargs):
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
        ingest.issues,
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
                                        "labels": {"nodes": [{"name": "good first issue"}]},
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


def _pr_record(repo: str, number: int, issue: int | None, updated: datetime) -> PullRequestDifficultyRecord:
    return PullRequestDifficultyRecord(
        repo=repo,
        pr_number=number,
        pr_created_at=updated,
        pr_merged_at=updated,
        pr_additions=1,
        pr_deletions=1,
        pr_changed_files=1,
        issue_number=issue,
        issue_labels=[],
        author="alice",
        updated_at=updated,
    )


def test_fetch_org_merged_pr_difficulty_graphql_is_incremental(monkeypatch, tmp_path, mock_client):
    """Org merged-PR difficulty routes through the dataset store: full fetch, then delta-merge."""
    repos = [RepositoryRecord("org/repo1", "repo1", "org")]
    monkeypatch.setattr(
        ingest.incremental,
        "dataset_path",
        lambda resource, scope, fingerprint="all": tmp_path / f"{resource}_{scope}_{fingerprint}.json",
    )
    monkeypatch.setattr(ingest._common, "fetch_org_repos_graphql", lambda *_a, **_k: repos)

    def fake_batched(client, org, *, per_repo, **_kwargs):
        # Route the batched engine through the per-repo fallback so the mocks
        # below drive the store; batching itself is covered by test_batched.py.
        return [record for repo in repos for record in per_repo(repo)]

    monkeypatch.setattr(ingest.incremental, "fetch_org_records_batched", fake_batched)

    # Recent timestamps: a watermark older than full_refresh_after would force
    # a second full fetch instead of exercising the delta path.
    r1 = _pr_record("org/repo1", 1, 10, datetime.now(UTC))
    r2 = _pr_record("org/repo1", 2, None, datetime.now(UTC))
    full = Mock(return_value=[r1])
    delta = Mock(return_value=[r1, r2])  # re-sends r1 (must dedup) + a new unlinked r2
    monkeypatch.setattr(ingest.pull_requests, "fetch_repo_merged_pr_difficulty_graphql", full)
    monkeypatch.setattr(ingest.pull_requests, "fetch_repo_merged_pr_difficulty_since_graphql", delta)

    first = ingest.fetch_org_merged_pr_difficulty_graphql(mock_client, "org", max_workers=2)
    assert first == [r1]
    full.assert_called_once()

    second = ingest.fetch_org_merged_pr_difficulty_graphql(mock_client, "org", max_workers=2)
    delta.assert_called_once()
    assert len(second) == 2  # r1 deduped by (repo, pr, issue) key, r2 added
    assert {r.pr_number for r in second} == {1, 2}


def test_merged_pr_without_linked_issue_yields_unlinked_record():
    """A merged PR with no closing-issue link still yields one (unlinked) record."""
    node = {
        "number": 11,
        "createdAt": "2024-01-01T00:00:00Z",
        "mergedAt": "2024-01-02T00:00:00Z",
        "updatedAt": "2024-01-03T00:00:00Z",
        "additions": 5,
        "deletions": 3,
        "changedFiles": 2,
        "author": {"login": "alice"},
        "closingIssuesReferences": {"nodes": []},
    }

    records = PullRequestDifficultyRecord.from_github_node(node, {"owner": "org", "repo": "repo"})

    assert len(records) == 1
    record = records[0]
    assert record.issue_number is None
    assert record.issue_labels == []
    assert record.author == "alice"
    assert record.updated_at == datetime(2024, 1, 3, tzinfo=UTC)


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
        mock_client,
        "org",
        "repo",
        states=["OPEN"],
        use_cache=False,
    )

    assert [(e.issue_number, e.event_type, e.label) for e in events] == [
        (1, "labeled", "beginner"),
        (1, "unlabeled", "beginner"),
    ]
    assert all(e.repo == "org/repo" for e in events)


def test_fetch_repo_issue_label_events_graphql_uses_stable_cache_key(
    mock_client,
    bypass_pagination,
    monkeypatch,
):
    """Cache key must not embed a per-run timestamp (guards the since-churn bug)."""
    _ = bypass_pagination
    mock_client.graphql.return_value = _label_events_payload()

    captured: dict[str, object] = {}

    def fake_load(kind, scope, parameters, _record_type, **_kwargs):
        captured["kind"] = kind
        captured["scope"] = scope
        captured["parameters"] = parameters  # cache miss -> implicit return None

    monkeypatch.setattr(ingest._common, "load_records_cache", fake_load)
    monkeypatch.setattr(ingest._common, "save_records_cache", lambda *_a, **_k: None)

    ingest.fetch_repo_issue_label_events_graphql(mock_client, "org", "repo", states=["OPEN"])

    assert captured["scope"] == "org_repo"
    assert captured["parameters"] == {"owner": "org", "repo": "repo", "states": ["OPEN"]}
    # No volatile time component anywhere in the key.
    assert "since" not in captured["parameters"]


def _repo(name):
    # NB: Mock(name=...) sets the mock's repr name, not .name, so assign after.
    repo = Mock(owner="o", full_name=f"o/{name}")
    repo.name = name
    return repo


def test_fetch_org_resource_parallel_recovers_transient_then_raises_partial(monkeypatch):
    """A repo that fails once recovers on retry; one that fails twice raises partial."""
    repos = [_repo("flaky"), _repo("broken"), _repo("ok")]
    monkeypatch.setattr(ingest._common, "fetch_org_repos_graphql", lambda _c, _o: repos)

    calls: dict[str, int] = {}

    def per_repo(repo):
        calls[repo.name] = calls.get(repo.name, 0) + 1
        if repo.name == "ok":
            return ["ok-rec"]
        if repo.name == "flaky" and calls["flaky"] >= 2:
            return ["flaky-rec"]  # succeeds on the retry pass
        raise RuntimeError("transient/permanent failure")

    with pytest.raises(PartialOrgFetchError) as excinfo:
        ingest.fetch_org_resource_parallel(Mock(), "org", per_repo, 4, task_desc="test")

    exc = excinfo.value
    # Records that DID arrive are carried so the store can still merge them.
    assert set(exc.records) == {"ok-rec", "flaky-rec"}  # flaky recovered on retry
    assert [r.name for r in exc.failed_repos] == ["broken"]  # only the twice-failer
    assert calls["flaky"] == 2  # retried once, then succeeded
    assert calls["broken"] == 2  # retried once, then given up


def test_fetch_org_resource_parallel_returns_all_when_every_repo_succeeds(monkeypatch):
    """With no failures, all records are returned and nothing is raised."""
    repos = [_repo("a"), _repo("b")]
    monkeypatch.setattr(ingest._common, "fetch_org_repos_graphql", lambda _c, _o: repos)

    result = ingest.fetch_org_resource_parallel(Mock(), "org", lambda repo: [f"{repo.name}-rec"], 4, task_desc="test")

    assert set(result) == {"a-rec", "b-rec"}


def test_fetch_org_resource_parallel_raises_partial_instead_of_returning_incomplete(monkeypatch):
    """A repo failing even after the retry raises PartialOrgFetchError, not a partial list."""
    repos = [_repo("ok"), _repo("broken")]
    monkeypatch.setattr(ingest._common, "fetch_org_repos_graphql", lambda *_a, **_k: repos)

    def fetch_repo(repo):
        if repo.name == "broken":
            raise RuntimeError("persistent failure")
        return [f"{repo.name}-rec"]

    with pytest.raises(PartialOrgFetchError) as excinfo:
        ingest.fetch_org_resource_parallel(Mock(), "org", fetch_repo, 4)

    assert excinfo.value.records == ["ok-rec"]
    assert [r.name for r in excinfo.value.failed_repos] == ["broken"]


# ---------------------------------------------------------
# merged-PR incremental delta: the real page loop + watermark early-stop
# ---------------------------------------------------------


def _pr_node(number: int, updated: str) -> dict:
    """A merged-PR GraphQL node with an unlinked closing issue."""
    return {
        "number": number,
        "createdAt": "2024-01-01T00:00:00Z",
        "mergedAt": updated,
        "updatedAt": updated,
        "additions": 1,
        "deletions": 1,
        "changedFiles": 1,
        "author": {"login": "alice"},
        "closingIssuesReferences": {"nodes": []},
    }


def _pr_page(nodes: list[dict], *, cursor: str | None, has_next: bool) -> dict:
    """Wrap PR nodes in the repository.pullRequests GraphQL envelope."""
    return {
        "data": {
            "repository": {
                "pullRequests": {
                    "nodes": nodes,
                    "pageInfo": {"endCursor": cursor, "hasNextPage": has_next},
                }
            }
        }
    }


def test_merged_pr_since_stops_paginating_past_the_watermark(mock_client):
    """The delta fetcher walks UPDATED_AT-descending pages and stops once one predates `since`.

    Boundary-page records older than `since` are still returned (the incremental
    merge is an idempotent upsert), but no further page is requested.
    """
    since = datetime(2024, 6, 1, tzinfo=UTC)

    pages = [
        _pr_page([_pr_node(1, "2024-07-01T00:00:00Z")], cursor="c1", has_next=True),
        # This page contains a PR older than the watermark -> pagination must stop here.
        _pr_page([_pr_node(2, "2024-05-01T00:00:00Z")], cursor="c2", has_next=True),
    ]
    mock_client.graphql = Mock(side_effect=pages)

    records = ingest.pull_requests.fetch_repo_merged_pr_difficulty_since_graphql(mock_client, "org", "repo", since)

    assert {r.pr_number for r in records} == {1, 2}  # boundary record still returned
    assert mock_client.graphql.call_count == 2  # did NOT request a third page
