"""Tests for the github_search data source module."""

from unittest.mock import Mock, patch

import pytest
import requests

import hiero_analytics.data_sources.github_search as search

# ---------------------------------------------------------
# fixtures
# ---------------------------------------------------------


@pytest.fixture
def mock_client():
    """Return a Mock object standing in for GitHubClient."""
    return Mock()


@pytest.fixture
def bypass_pagination(monkeypatch):
    """Replace paginate_page_number so only one page executes."""
    monkeypatch.setattr(
        search,
        "paginate_page_number",
        lambda f, **_kwargs: f(1),
    )


# ---------------------------------------------------------
# basic search
# ---------------------------------------------------------


def test_search_issues_returns_items(mock_client, bypass_pagination):
    """Test that search_issues returns normalized records from the API response."""
    mock_client.get.return_value = {
        "items": [
            {
                "number": 1,
                "title": "issue1",
                "state": "open",
                "created_at": "2024-01-01T00:00:00Z",
                "repository_url": "https://api.github.com/repos/org/repo",
                "user": {"login": "alice"},
                "labels": [{"name": "bug"}],
                "html_url": "https://github.com/org/repo/issues/1",
            },
            {"number": 2, "title": "issue2", "pull_request": {}},
        ]
    }

    results = search.search_issues(mock_client, "label:bug")

    assert len(results) == 2
    first = results[0]
    assert first.number == 1
    assert first.repo == "org/repo"
    assert first.author == "alice"
    assert first.labels == ["bug"]
    assert first.created_at is not None
    assert not first.is_pull_request
    assert results[1].is_pull_request


# ---------------------------------------------------------
# request parameters
# ---------------------------------------------------------


def test_search_issues_calls_request_correctly(mock_client, bypass_pagination):
    """Test that search_issues sends the correct URL and query parameters."""
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
    """Test that non-dict and malformed items in the API response are filtered out."""
    mock_client.get.return_value = {
        "items": [
            {"number": 1},
            "bad",
            None,
            {"title": "no number"},
            {"number": 2},
        ]
    }

    results = search.search_issues(mock_client, "test")

    assert [r.number for r in results] == [1, 2]


# ---------------------------------------------------------
# empty response
# ---------------------------------------------------------


def test_search_issues_handles_missing_items(mock_client, bypass_pagination):
    """Test that a response missing the items key returns an empty list."""
    mock_client.get.return_value = {}

    results = search.search_issues(mock_client, "test")

    assert results == []


# ---------------------------------------------------------
# pagination integration
# ---------------------------------------------------------


def test_search_issues_uses_pagination(monkeypatch, mock_client):
    """Test that search_issues delegates to the paginator."""
    called = {"value": False}

    def fake_paginator(page_func, **_kwargs):
        called["value"] = True
        return page_func(1)

    monkeypatch.setattr(search, "paginate_page_number", fake_paginator)

    mock_client.get.return_value = {"items": []}

    search.search_issues(mock_client, "test")

    assert called["value"] is True


# ---------------------------------------------------------
# 1000-result search cap
# ---------------------------------------------------------


def _capture_paginator_kwargs(monkeypatch, mock_client):
    """Replace the paginator with one that records its keyword arguments."""
    captured = {}

    def fake_paginator(page_func, **kwargs):
        captured.update(kwargs)
        return page_func(1)

    monkeypatch.setattr(search, "paginate_page_number", fake_paginator)
    mock_client.get.return_value = {"items": []}
    return captured


def test_search_issues_caps_pages_at_search_limit(monkeypatch, mock_client):
    """Pagination never goes past GitHub's 1000-result boundary (page 11 would 422)."""
    captured = _capture_paginator_kwargs(monkeypatch, mock_client)

    search.search_issues(mock_client, "test")

    assert captured["max_pages"] == search._SEARCH_MAX_PAGES


def test_search_issues_clamps_caller_max_pages(monkeypatch, mock_client):
    """A caller-supplied max_pages beyond the API cap is clamped; a smaller one is kept."""
    captured = _capture_paginator_kwargs(monkeypatch, mock_client)

    search.search_issues(mock_client, "test", max_pages=50)
    assert captured["max_pages"] == search._SEARCH_MAX_PAGES

    search.search_issues(mock_client, "test", max_pages=3)
    assert captured["max_pages"] == 3


def test_search_issues_warns_on_truncated_result_set(mock_client, bypass_pagination, caplog):
    """A query matching more than 1000 results logs a truncation warning."""
    mock_client.get.return_value = {"total_count": 2500, "items": [{"id": 1}]}

    with caplog.at_level("WARNING"):
        search.search_issues(mock_client, "test")

    assert any("first 1000" in message for message in caplog.messages)


def test_search_issues_warns_on_incomplete_results(mock_client, bypass_pagination, caplog):
    """GitHub's incomplete_results flag (query timeout) is surfaced as a warning."""
    mock_client.get.return_value = {"incomplete_results": True, "items": [{"id": 1}]}

    with caplog.at_level("WARNING"):
        search.search_issues(mock_client, "test")

    assert any("incomplete" in message for message in caplog.messages)


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


def _http_error(status_code):
    response = Mock()
    response.status_code = status_code
    return requests.HTTPError(response=response)


@patch("hiero_analytics.data_sources.github_client.GitHubClient")
def test_has_codeowners_file_404_means_absent(mock_client):
    """A 404 on every standard path reports the file as absent."""
    mock_client.get.side_effect = _http_error(404)

    result = search.has_codeowners_file(mock_client, "hiero-ledger", "hiero-sdk-python")

    assert result is False
    assert mock_client.get.call_count == 3


@patch("hiero_analytics.data_sources.github_client.GitHubClient")
def test_has_codeowners_file_other_errors_propagate(mock_client):
    """A non-404 failure raises instead of being reported as a missing file."""
    mock_client.get.side_effect = _http_error(403)

    with pytest.raises(requests.HTTPError):
        search.has_codeowners_file(mock_client, "hiero-ledger", "hiero-sdk-python")


@patch("hiero_analytics.data_sources.github_client.GitHubClient")
def test_fetch_repo_workflows_mock_api(mock_client):
    """Test workflow fetching and yml parsing using mocked GitHub responses."""
    mock_client.get.side_effect = [
        [{"name": "ci.yml", "url": "api.github.com/ci_yml_url"}],
        {"content": "bmFtZTogQ0kKam9iczogCiAgYnVpbGQ6CiAgICBydW5zLW9uOiBobC1zZGstcHktbGluLW1k"},
    ]

    results = search.fetch_repo_workflows(mock_client, "hiero-ledger", "hiero-sdk-python")

    assert len(results) == 1
    job = results[0]
    assert job.repo == "hiero-sdk-python"
    assert job.workflow_file == "ci.yml"
    assert job.job_name == "build"
    assert job.runner == "hl-sdk-py-lin-md"
    assert job.is_self_hosted is True


@patch("hiero_analytics.data_sources.github_client.GitHubClient")
def test_fetch_repo_workflows_empty_dir(mock_client):
    """Test returns empty list when no workflow directory exists."""
    mock_client.get.return_value = None

    results = search.fetch_repo_workflows(mock_client, "hiero-ledger", "empty-repo")

    assert results == []
