"""Tests for GitHub REST API interactions."""

from unittest.mock import Mock

import pytest

import hiero_analytics.data_sources.github_search as search

# --------------------------------------------------------
# fixtures
# --------------------------------------------------------


@pytest.fixture
def mock_client():
    """Mock GitHub client fixture."""
    return Mock()


@pytest.fixture
def bypass_pagination(monkeypatch):
    """Replace paginate_page_number so only one page runs."""
    monkeypatch.setattr(
        search,
        "paginate_page_number",
        lambda f, **_kwargs: f(1),
    )


# --------------------------------------------------------
# basic success case
# --------------------------------------------------------


def test_search_issues_returns_items(mock_client, bypass_pagination):
    """Test searching issues returns normalized records."""
    mock_client.get.return_value = {
        "items": [
            {"number": 1, "title": "Issue A"},
            {"number": 2, "title": "Issue B"},
        ]
    }

    results = search.search_issues(mock_client, "label:bug")

    assert len(results) == 2
    assert results[0].number == 1
    assert results[0].title == "Issue A"


# --------------------------------------------------------
# request parameters
# --------------------------------------------------------


def test_search_issues_calls_client_with_correct_params(mock_client, bypass_pagination):
    """Test searching issues calls client with proper request parameters."""
    mock_client.get.return_value = {"items": []}

    search.search_issues(mock_client, "repo:org/repo is:issue")

    mock_client.get.assert_called_once()

    args, kwargs = mock_client.get.call_args

    assert args[0] == "https://api.github.com/search/issues"

    params = kwargs["params"]

    assert params["q"] == "repo:org/repo is:issue"
    assert params["per_page"] == 100
    assert params["page"] == 1


# --------------------------------------------------------
# filtering invalid items
# --------------------------------------------------------


def test_search_issues_filters_non_dict_items(mock_client, bypass_pagination):
    """Test searching issues filters out invalid non-dictionary items."""
    mock_client.get.return_value = {
        "items": [
            {"number": 1},
            None,
            "bad",
            {"number": 2},
        ]
    }

    results = search.search_issues(mock_client, "test")

    assert [r.number for r in results] == [1, 2]


# --------------------------------------------------------
# missing items key
# --------------------------------------------------------


def test_search_issues_handles_missing_items(mock_client, bypass_pagination):
    """Test searching issues gracefully handles missing items key in response."""
    mock_client.get.return_value = {}

    results = search.search_issues(mock_client, "test")

    assert results == []


# --------------------------------------------------------
# paginator integration
# --------------------------------------------------------


def test_search_issues_uses_paginator(monkeypatch, mock_client):
    """Test searching issues uses the paginator helper."""
    called = {"value": False}

    def fake_paginator(page_fn, **_kwargs):
        called["value"] = True
        return page_fn(1)

    monkeypatch.setattr(search, "paginate_page_number", fake_paginator)

    mock_client.get.return_value = {"items": []}

    search.search_issues(mock_client, "test")

    assert called["value"] is True
