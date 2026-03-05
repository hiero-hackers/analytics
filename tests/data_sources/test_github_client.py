import os
from unittest.mock import Mock

import pytest

import hiero_analytics.data_sources.github_client as github_client


@pytest.fixture
def mock_sleep(monkeypatch):
    """Prevent real sleep during tests."""
    monkeypatch.setattr(github_client.time, "sleep", lambda x: None)


def test_client_sets_auth_header(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    client = github_client.GitHubClient()

    assert client.headers["Authorization"] == "Bearer test-token"


def test_client_without_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    client = github_client.GitHubClient()

    assert client.headers == {}


def test_get_success(monkeypatch, mock_sleep):

    mock_response = Mock()
    mock_response.headers = {
        "X-RateLimit-Remaining": "10",
        "X-RateLimit-Reset": "0",
    }
    mock_response.json.return_value = {"hello": "world"}
    mock_response.raise_for_status = Mock()

    mock_get = Mock(return_value=mock_response)
    monkeypatch.setattr(github_client.requests, "get", mock_get)

    client = github_client.GitHubClient()

    result = client.get("https://api.github.com/test")

    assert result == {"hello": "world"}
    mock_get.assert_called_once()


def test_get_rate_limit_retry(monkeypatch, mock_sleep):

    first = Mock()
    first.headers = {
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": "0",
    }
    first.raise_for_status = Mock()
    first.json.return_value = {}

    second = Mock()
    second.headers = {
        "X-RateLimit-Remaining": "10",
        "X-RateLimit-Reset": "0",
    }
    second.raise_for_status = Mock()
    second.json.return_value = {"retried": True}

    mock_get = Mock(side_effect=[first, second])
    monkeypatch.setattr(github_client.requests, "get", mock_get)

    client = github_client.GitHubClient()

    result = client.get("https://api.github.com/test")

    assert result == {"retried": True}
    assert mock_get.call_count == 2


def test_graphql_request(monkeypatch):

    mock_response = Mock()
    mock_response.json.return_value = {"data": {"ok": True}}
    mock_response.raise_for_status = Mock()

    mock_post = Mock(return_value=mock_response)
    monkeypatch.setattr(github_client.requests, "post", mock_post)

    client = github_client.GitHubClient()

    query = "query { viewer { login } }"
    variables = {"a": 1}

    result = client.graphql(query, variables)

    assert result == {"data": {"ok": True}}

    mock_post.assert_called_once()

    args, kwargs = mock_post.call_args

    assert kwargs["json"]["query"] == query
    assert kwargs["json"]["variables"] == variables