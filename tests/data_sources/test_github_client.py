"""Tests for the GitHubClient HTTP client."""

import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

import hiero_analytics.data_sources.github_client as github_client

# ---------------------------------------------------------
# FIXTURE: disable sleeping
# ---------------------------------------------------------


@pytest.fixture
def mock_sleep(monkeypatch):
    """Disable actual sleeping in tests by replacing time.sleep with a no-op."""
    monkeypatch.setattr(github_client.time, "sleep", lambda _: None)


# ---------------------------------------------------------
# HEADER TESTS
# ---------------------------------------------------------


def test_client_sets_auth_header(monkeypatch):
    """Verify the client sets Authorization header when a token is available."""
    monkeypatch.setattr(github_client, "GITHUB_TOKEN", "test-token")

    client = github_client.GitHubClient()

    assert client.session.headers["Authorization"] == "Bearer test-token"


def test_client_without_token(monkeypatch):
    """Verify no Authorization header is set when no token is provided."""
    monkeypatch.setattr(github_client, "GITHUB_TOKEN", None)

    client = github_client.GitHubClient()

    assert "Authorization" not in client.session.headers


# ---------------------------------------------------------
# BASIC GET
# ---------------------------------------------------------


def test_get_success(monkeypatch, mock_sleep):
    """Verify a successful GET request returns parsed JSON and increments request counter."""
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


def test_no_retry_on_401(monkeypatch, mock_sleep):
    """Verify the client fails immediately on 401 Unauthorized."""
    client = github_client.GitHubClient()

    mock_response = Mock()
    mock_response.status_code = 401
    mock_response.ok = False
    mock_response.headers = {}

    mock_response.raise_for_status.side_effect = requests.HTTPError("401 Client Error")

    request_mock = Mock(return_value=mock_response)
    monkeypatch.setattr(client.session, "request", request_mock)

    with pytest.raises(requests.HTTPError):
        client.get("https://api.github.com/test")

    assert request_mock.call_count == 1


# ---------------------------------------------------------
# RATE LIMIT RETRY
# ---------------------------------------------------------


def test_get_rate_limit_retry(monkeypatch, mock_sleep):
    """Verify the client retries after a 403 rate-limit response."""
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


def test_retries_on_502_and_succeeds(monkeypatch, mock_sleep):
    """Verify the client recovers if a 502 is followed by a 200."""
    client = github_client.GitHubClient()

    fail_502 = Mock()
    fail_502.status_code = 502
    fail_502.ok = False
    fail_502.headers = {}

    success_200 = Mock()
    success_200.status_code = 200
    success_200.ok = True
    success_200.headers = {"X-RateLimit-Remaining": "5000"}
    success_200.json.return_value = {"data": "recovered"}

    request_mock = Mock(side_effect=[fail_502, success_200])
    monkeypatch.setattr(client.session, "request", request_mock)

    result = client.get("https://api.github.com/test")

    assert result == {"data": "recovered"}
    assert request_mock.call_count == 2


def test_502_prioritized_over_rate_limit(monkeypatch, mock_sleep):
    """Verify the 502 retry path takes priority over rate-limit handling."""
    client = github_client.GitHubClient()

    fail_502 = Mock()
    fail_502.status_code = 502
    fail_502.ok = False
    fail_502.headers = {
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": "0",
    }

    success = Mock()
    success.status_code = 200
    success.ok = True
    success.headers = {"X-RateLimit-Remaining": "10"}
    success.json.return_value = {"ok": True}

    request_mock = Mock(side_effect=[fail_502, success])
    monkeypatch.setattr(client.session, "request", request_mock)

    result = client.get("https://api.github.com/test")

    assert result == {"ok": True}
    assert request_mock.call_count == 2


# ---------------------------------------------------------
# CONCURRENCY
# ---------------------------------------------------------


def test_counter_thread_safety(monkeypatch):
    """Verify requests_made is accurate when hit by multiple threads."""
    client = github_client.GitHubClient()

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.ok = True
    mock_response.headers = {"X-RateLimit-Remaining": "5000"}
    mock_response.json.return_value = {}

    monkeypatch.setattr(client.session, "request", Mock(return_value=mock_response))

    # Run 10 threads at once
    threads = [threading.Thread(target=client.get, args=("url",)) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert client.requests_made == 10


# ---------------------------------------------------------
# GRAPHQL
# ---------------------------------------------------------


def test_graphql_request(monkeypatch):
    """Verify a GraphQL query is sent with the correct payload structure."""
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
    """Verify a RuntimeError is raised when GraphQL rate-limit retries are exhausted."""
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


def test_graphql_rate_limit_sleep_never_aborts_the_retry(monkeypatch):
    """Arbitrarily long rate-limit sleeps (policy or transport) must end in a retry.

    There is deliberately no wall-clock budget on the GraphQL loop — it is
    attempt-bounded — so even an hour-long reset wait recovers instead of
    raising TimeoutError.
    """
    clock = {"now": 1_000.0}
    fake_time = SimpleNamespace(
        time=lambda: clock["now"],
        sleep=lambda seconds: clock.__setitem__("now", clock["now"] + seconds),
    )
    monkeypatch.setattr(github_client, "time", fake_time)

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

    recovered = Mock()
    recovered.raise_for_status = Mock()
    recovered.headers = {}
    recovered.status_code = 200
    recovered.ok = True
    recovered.json.return_value = {"data": {"viewer": {"login": "octocat"}}}

    client = github_client.GitHubClient()

    request_mock = Mock(side_effect=[rate_limited, recovered])
    monkeypatch.setattr(client.session, "request", request_mock)

    result = client.graphql("query { viewer { login } }", {})

    assert result == {"data": {"viewer": {"login": "octocat"}}}
    assert request_mock.call_count == 2
