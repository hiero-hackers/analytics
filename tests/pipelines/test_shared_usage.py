"""Tests for the shared-client usage helpers."""

from hiero_analytics.pipelines import _shared


def test_usage_summary_without_a_client_is_empty_and_builds_no_client(monkeypatch):
    """Asking for usage must not construct a client (and warn about a missing token)."""
    monkeypatch.setattr(_shared, "_client", None)

    summary = _shared.api_usage_summary()

    assert summary["total"] == {"rest_requests": 0, "graphql_requests": 0, "graphql_points": 0}
    assert _shared._client is None


def test_reset_without_a_client_is_a_no_op(monkeypatch):
    """There is nothing to reset before the first client exists."""
    monkeypatch.setattr(_shared, "_client", None)

    _shared.reset_api_usage()

    assert _shared._client is None


def test_usage_summary_reads_the_shared_clients_ledger(monkeypatch):
    """With a client, the summary is that client's ledger."""
    client = _shared.GitHubClient()
    monkeypatch.setattr(_shared, "_client", client)
    client.usage.record_request(graphql=False)

    assert _shared.api_usage_summary()["total"]["rest_requests"] == 1

    _shared.reset_api_usage()

    assert _shared.api_usage_summary()["total"]["rest_requests"] == 0
