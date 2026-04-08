from unittest.mock import Mock, patch

import pytest

import hiero_analytics.data_sources.github_search as search

# ---------------------------------------------------------
# fixtures
# ---------------------------------------------------------

@pytest.fixture
def mock_client():
    return Mock()


@pytest.fixture
def bypass_pagination(monkeypatch):
    """
    Replace paginate_page_number so only one page executes.
    """
    monkeypatch.setattr(
        search,
        "paginate_page_number",
        lambda f: f(1),
    )


# ---------------------------------------------------------
# basic search
# ---------------------------------------------------------

def test_search_issues_returns_items(mock_client, bypass_pagination):

    mock_client.get.return_value = {
        "items": [
            {"id": 1, "title": "issue1"},
            {"id": 2, "title": "issue2"},
        ]
    }

    results = search.search_issues(mock_client, "label:bug")

    assert len(results) == 2
    assert results[0]["id"] == 1


# ---------------------------------------------------------
# request parameters
# ---------------------------------------------------------

def test_search_issues_calls_request_correctly(mock_client, bypass_pagination):

    mock_client.get.return_value = {"items": []}

    search.search_issues(mock_client, "repo:org/repo is:issue")

    args, kwargs = mock_client.get.call_args

    assert args[0] == "https://api.github.com/search/issues"

    params = kwargs["params"]

    assert params["q"] == "repo:org/repo is:issue"
    assert params["per_page"] == 100
    assert params["page"] == 1


# ---------------------------------------------------------
# filters non-dict items
# ---------------------------------------------------------

def test_search_issues_filters_invalid_items(mock_client, bypass_pagination):

    mock_client.get.return_value = {
        "items": [
            {"id": 1},
            "bad",
            None,
            {"id": 2},
        ]
    }

    results = search.search_issues(mock_client, "test")

    assert len(results) == 2
    assert all(isinstance(i, dict) for i in results)


# ---------------------------------------------------------
# empty response
# ---------------------------------------------------------

def test_search_issues_handles_missing_items(mock_client, bypass_pagination):

    mock_client.get.return_value = {}

    results = search.search_issues(mock_client, "test")

    assert results == []


# ---------------------------------------------------------
# pagination integration
# ---------------------------------------------------------

def test_search_issues_uses_pagination(monkeypatch, mock_client):

    called = {"value": False}

    def fake_paginator(page_func):
        called["value"] = True
        return page_func(1)

    monkeypatch.setattr(search, "paginate_page_number", fake_paginator)

    mock_client.get.return_value = {"items": []}

    search.search_issues(mock_client, "test")

    assert called["value"] is True


@patch("hiero_analytics.data_sources.github_client.GitHubClient")
def test_has_codeowners_file_found(mock_client):
    """Test returns True when a codeowners file is found at a specific path."""
    mock_client.get.side_effect = lambda url: {"name": "CO"} if ".github/CODEOWNERS" in url else None

    result = search.has_codeowners_file(mock_client, "hiero-ledger", "hiero-sdk-python")
        
    assert result is True
    assert mock_client.get.call_count == 1


@patch("hiero_analytics.data_sources.github_client.GitHubClient")
def test_has_codeowners_file_not_found(mock_client):
    """Test returns False when no paths return a valid response."""
    mock_client.get.return_value = None

    result = search.has_codeowners_file(mock_client, "hiero-ledger", "hiero-sdk-python")
    
    assert result is False
    assert mock_client.get.call_count == 3


@patch("hiero_analytics.data_sources.github_client.GitHubClient")
def test_fetch_repo_workflows_mock_api(mock_client):
    """Test workflow fetching and yml parsing using mocked GitHub responses."""
    mock_client.get.side_effect = [
        [{"name": "ci.yml", "url": "api.github.com/ci_yml_url"}],
        {
            "content": "bmFtZTogQ0kKam9iczogCiAgYnVpbGQ6CiAgICBydW5zLW9uOiBobC1zZGstcHktbGluLW1k" 
        }
    ]

    results = search.fetch_repo_workflows(mock_client, "hiero-ledger", "hiero-sdk-python")

    assert len(results) == 1
    job = results[0]
    assert job["file"] == "ci.yml"
    assert job["job"] == "build"
    assert job["runner"] == "hl-sdk-py-lin-md"
    assert job["is_self_hosted"] is True


@patch("hiero_analytics.data_sources.github_client.GitHubClient")
def test_fetch_repo_workflows_empty_dir(mock_client):
    """Test returns empty list when no workflow directory exists."""
    mock_client.get.return_value = None

    results = search.fetch_repo_workflows(mock_client, "hiero-ledger", "empty-repo")
    
    assert results == []

