from unittest.mock import Mock

import pytest

import hiero_analytics.data_sources.github_client as github_client

# ---------------------------------------------------------
# FIXTURE: disable sleeping
# ---------------------------------------------------------

@pytest.fixture
def mock_sleep(monkeypatch):
    monkeypatch.setattr(github_client.time, "sleep", lambda x: None)


# ---------------------------------------------------------
# HEADER TESTS
# ---------------------------------------------------------

def test_client_sets_auth_header(monkeypatch):

    monkeypatch.setattr(github_client, "GITHUB_TOKEN", "test-token")

    client = github_client.GitHubClient()

    assert client.session.headers["Authorization"] == "Bearer test-token"


def test_client_without_token(monkeypatch):

    monkeypatch.setattr(github_client, "GITHUB_TOKEN", None)

    client = github_client.GitHubClient()

    assert "Authorization" not in client.session.headers


# ---------------------------------------------------------
# BASIC GET
# ---------------------------------------------------------

def test_get_success(monkeypatch, mock_sleep):

    mock_response = Mock()
    mock_response.headers = {
        "X-RateLimit-Remaining": "10",
        "X-RateLimit-Reset": "0",
    }
    mock_response.json.return_value = {"hello": "world"}
    mock_response.raise_for_status = Mock()
    mock_response.status_code = 200
    mock_response.ok = True

    client = github_client.GitHubClient()

    monkeypatch.setattr(
        client.session,
        "request",
        Mock(return_value=mock_response),
    )

    result = client.get("https://api.github.com/test")

    assert result == {"hello": "world"}
    assert client.requests_made == 1


# ---------------------------------------------------------
# RATE LIMIT RETRY
# ---------------------------------------------------------

def test_get_rate_limit_retry(monkeypatch, mock_sleep):

    first = Mock()
    first.headers = {
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": "0",
    }
    first.raise_for_status = Mock()
    first.json.return_value = {}
    first.status_code = 403
    first.ok = False

    second = Mock()
    second.headers = {
        "X-RateLimit-Remaining": "10",
        "X-RateLimit-Reset": "0",
    }
    second.raise_for_status = Mock()
    second.json.return_value = {"retried": True}
    second.status_code = 200
    second.ok = True

    client = github_client.GitHubClient()

    monkeypatch.setattr(
        client.session,
        "request",
        Mock(side_effect=[first, second]),
    )

    result = client.get("https://api.github.com/test")

    assert result == {"retried": True}


# ---------------------------------------------------------
# GRAPHQL
# ---------------------------------------------------------

def test_graphql_request(monkeypatch):

    mock_response = Mock()
    mock_response.json.return_value = {"data": {"ok": True}}
    mock_response.raise_for_status = Mock()
    mock_response.headers = {}
    mock_response.status_code = 200
    mock_response.ok = True

    client = github_client.GitHubClient()

    request_mock = Mock(return_value=mock_response)

    monkeypatch.setattr(client.session, "request", request_mock)

    query = "query { viewer { login } }"
    variables = {"a": 1}

    result = client.graphql(query, variables)

    assert result == {"data": {"ok": True}}

    args, kwargs = request_mock.call_args

    assert kwargs["json"]["query"] == query
    assert kwargs["json"]["variables"] == variables


def test_graphql_fresh_retry_limit_exceeded(monkeypatch, mock_sleep):

    rate_limited = Mock()
    rate_limited.raise_for_status = Mock()
    rate_limited.headers = {}
    rate_limited.status_code = 200
    rate_limited.ok = True
    rate_limited.json.return_value = {
        "data": {
            "rateLimit": {
                "remaining": 0,
                "limit": 5000,
                "cost": 1,
                "resetAt": "2099-01-01T00:00:00Z",
            }
        },
        "errors": [{"type": "RATE_LIMIT"}],
    }

    client = github_client.GitHubClient()

    monkeypatch.setattr(
        client.session,
        "request",
        Mock(return_value=rate_limited),
    )

    with pytest.raises(RuntimeError, match="GraphQL fresh retry limit exceeded"):
        client.graphql("query { viewer { login } }", {})