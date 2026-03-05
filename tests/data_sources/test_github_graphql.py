from unittest.mock import Mock

import hiero_analytics.data_sources.github_graphql as graphql


def test_fetch_org_repos_graphql(monkeypatch):
    client = Mock()

    fake_response = {
        "data": {
            "organization": {
                "repositories": {
                    "nodes": [{"name": "repo1"}, {"name": "repo2"}],
                    "pageInfo": {
                        "hasNextPage": False,
                        "endCursor": None,
                    },
                }
            }
        }
    }

    client.graphql.return_value = fake_response

    # bypass real paginator
    monkeypatch.setattr(
        graphql,
        "paginate_cursor",
        lambda f: f(None)[0],
    )

    repos = graphql.fetch_org_repos_graphql(client, "org")

    assert repos == ["repo1", "repo2"]


def test_fetch_repo_issues_graphql(monkeypatch):
    client = Mock()

    fake_response = {
        "data": {
            "repository": {
                "issues": {
                    "nodes": [
                        {
                            "number": 1,
                            "title": "Issue A",
                            "state": "OPEN",
                            "createdAt": "2024-01-01",
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

    client.graphql.return_value = fake_response

    monkeypatch.setattr(
        graphql,
        "paginate_cursor",
        lambda f: f(None)[0],
    )

    issues = graphql.fetch_repo_issues_graphql(client, "org", "repo1")

    assert len(issues) == 1
    assert issues[0]["repo"] == "repo1"
    assert issues[0]["number"] == 1
    assert issues[0]["labels"] == ["bug"]


def test_fetch_org_issues_graphql_parallel(monkeypatch):
    client = Mock()

    # mock repo discovery
    monkeypatch.setattr(
        graphql,
        "fetch_org_repos_graphql",
        lambda client, org: ["repo1", "repo2"],
    )

    # mock repo issue fetching
    monkeypatch.setattr(
        graphql,
        "fetch_repo_issues_graphql",
        lambda client, owner, repo: [{"repo": repo, "number": 1}],
    )

    issues = graphql.fetch_org_issues_graphql(client, "org", max_workers=2)

    repos = {i["repo"] for i in issues}

    assert repos == {"repo1", "repo2"}
    assert len(issues) == 2