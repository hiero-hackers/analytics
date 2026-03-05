from unittest.mock import Mock

import hiero_analytics.data_sources.github_search as github_search


def test_search_issues_returns_items(monkeypatch):

    client = Mock()

    fake_response = {
        "items": [
            {"id": 1, "title": "Issue A"},
            {"id": 2, "title": "Issue B"},
        ]
    }

    client.get.return_value = fake_response

    monkeypatch.setattr(
        github_search,
        "paginate_page_number",
        lambda f: f(1),
    )

    results = github_search.search_issues(
        client,
        'org:test label:"bug"',
    )

    assert len(results) == 2
    assert results[0]["title"] == "Issue A"


def test_search_issues_constructs_query_url(monkeypatch):

    client = Mock()
    client.get.return_value = {"items": []}

    monkeypatch.setattr(
        github_search,
        "paginate_page_number",
        lambda f: f(1),
    )

    query = 'org:hiero-ledger label:"good first issue"'

    github_search.search_issues(client, query)

    called_url = client.get.call_args[0][0]

    assert "search/issues" in called_url
    assert "per_page=100" in called_url
    assert query in called_url


def test_search_issues_handles_empty(monkeypatch):

    client = Mock()
    client.get.return_value = {"items": []}

    monkeypatch.setattr(
        github_search,
        "paginate_page_number",
        lambda f: f(1),
    )

    results = github_search.search_issues(client, "org:test")

    assert results == []