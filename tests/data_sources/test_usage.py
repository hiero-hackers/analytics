"""Tests for GitHub API usage attribution (scope, ledger, client, propagation)."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
import requests

import hiero_analytics.config.paths as paths
import hiero_analytics.data_sources.github_client as github_client
from hiero_analytics.data_sources.dataset_store import load_or_fetch
from hiero_analytics.data_sources.github_ingest._common import fetch_all_with_retry
from hiero_analytics.data_sources.github_ingest.incremental import OrgIncrementalResource, fetch_org_incremental
from hiero_analytics.data_sources.models import IssueTimelineEventRecord
from hiero_analytics.data_sources.usage import (
    UNATTRIBUTED,
    UsageLedger,
    UsageScope,
    current_scope,
    usage_scope,
)

# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------


@pytest.fixture
def mock_sleep(monkeypatch):
    """Disable real sleeping."""
    monkeypatch.setattr(github_client.time, "sleep", lambda _: None)


def _response(*, status: int = 200, payload: object = None, headers: dict | None = None) -> Mock:
    """A minimal fake ``requests.Response``."""
    response = Mock()
    response.status_code = status
    response.ok = status < 400
    response.headers = headers or {}
    response.json.return_value = payload if payload is not None else {}
    if status >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(f"{status}")
    return response


def _graphql_payload(*, cost: object = 1, remaining: object = 4990) -> dict:
    return {"data": {"rateLimit": {"cost": cost, "remaining": remaining, "limit": 5000, "resetAt": None}}}


# ---------------------------------------------------------
# SCOPE
# ---------------------------------------------------------


def test_default_scope_is_empty():
    """Outside any scope nothing is attributed."""
    assert current_scope() == UsageScope(None, None)


def test_scope_sets_and_restores():
    """The scope applies inside the block and is restored after it."""
    with usage_scope(org="acme", dataset="issues"):
        assert current_scope() == UsageScope("acme", "issues")
    assert current_scope() == UsageScope(None, None)


def test_inner_scope_inherits_unset_fields_and_restores_outer():
    """A nested scope only overrides what it names."""
    with usage_scope(org="acme"):
        with usage_scope(dataset="issues"):
            assert current_scope() == UsageScope("acme", "issues")
        assert current_scope() == UsageScope("acme", None)


def test_scope_restored_when_the_block_raises():
    """An exception must not leak the scope to later work."""
    with pytest.raises(RuntimeError), usage_scope(org="acme"):
        raise RuntimeError("boom")
    assert current_scope() == UsageScope(None, None)


# ---------------------------------------------------------
# LEDGER
# ---------------------------------------------------------


def test_ledger_attributes_requests_and_points_to_the_current_scope():
    """Requests and points land under the scope that was current when recorded."""
    ledger = UsageLedger()
    with usage_scope(org="acme", dataset="issues"):
        ledger.record_request(graphql=True)
        ledger.record_graphql_rate_limit(cost=3, remaining=4000)
        ledger.record_request(graphql=False)
    with usage_scope(org="other", dataset="prs"):
        ledger.record_request(graphql=True)
        ledger.record_graphql_rate_limit(cost=5, remaining=3900)

    summary = ledger.summary()

    assert summary["total"] == {"rest_requests": 1, "graphql_requests": 2, "graphql_points": 8}
    assert summary["graphql_remaining"] == 3900
    assert summary["orgs"]["acme"]["graphql_points"] == 3
    assert summary["orgs"]["acme"]["datasets"]["issues"] == {
        "rest_requests": 1,
        "graphql_requests": 1,
        "graphql_points": 3,
    }
    assert summary["orgs"]["other"]["datasets"]["prs"]["graphql_points"] == 5


def test_ledger_org_totals_roll_up_their_datasets():
    """An org's row is the sum of its dataset rows."""
    ledger = UsageLedger()
    for dataset, cost in (("issues", 2), ("prs", 7)):
        with usage_scope(org="acme", dataset=dataset):
            ledger.record_request(graphql=True)
            ledger.record_graphql_rate_limit(cost=cost, remaining=1)

    org = ledger.summary()["orgs"]["acme"]

    assert org["graphql_points"] == 9
    assert org["graphql_requests"] == 2
    assert sum(d["graphql_points"] for d in org["datasets"].values()) == org["graphql_points"]


def test_ledger_unscoped_requests_are_visible_not_dropped():
    """Work outside any scope shows up in the unattributed bucket."""
    ledger = UsageLedger()
    ledger.record_request(graphql=False)
    with usage_scope(org="acme"):
        ledger.record_request(graphql=False)

    orgs = ledger.summary()["orgs"]

    assert orgs[UNATTRIBUTED]["datasets"][UNATTRIBUTED]["rest_requests"] == 1
    assert orgs["acme"]["datasets"][UNATTRIBUTED]["rest_requests"] == 1
    assert ledger.summary()["total"]["rest_requests"] == 2


def test_ledger_empty_summary_is_all_zero():
    """A run that made no requests reports zeros, not an error."""
    summary = UsageLedger().summary()

    assert summary == {
        "total": {"rest_requests": 0, "graphql_requests": 0, "graphql_points": 0},
        "graphql_remaining": None,
        "orgs": {},
    }


@pytest.mark.parametrize("bad", [None, "7", 1.5, True])
def test_ledger_ignores_malformed_rate_limit_values(bad):
    """A malformed rateLimit block must not corrupt totals."""
    ledger = UsageLedger()
    with usage_scope(org="acme"):
        ledger.record_graphql_rate_limit(cost=bad, remaining=bad)

    summary = ledger.summary()

    assert summary["total"]["graphql_points"] == 0
    assert summary["graphql_remaining"] is None


def test_ledger_reset_clears_everything():
    """Reset starts a fresh run."""
    ledger = UsageLedger()
    with usage_scope(org="acme"):
        ledger.record_request(graphql=True)
        ledger.record_graphql_rate_limit(cost=4, remaining=10)

    ledger.reset()

    assert ledger.summary()["orgs"] == {}
    assert ledger.summary()["graphql_remaining"] is None


def test_ledger_is_thread_safe():
    """Concurrent recording loses no counts."""
    ledger = UsageLedger()

    def work() -> None:
        with usage_scope(org="acme", dataset="issues"):
            for _ in range(200):
                ledger.record_request(graphql=True)
                ledger.record_graphql_rate_limit(cost=1, remaining=1)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert ledger.summary()["total"] == {"rest_requests": 0, "graphql_requests": 1600, "graphql_points": 1600}


# ---------------------------------------------------------
# CLIENT ATTRIBUTION
# ---------------------------------------------------------


def test_client_attributes_rest_and_graphql_to_scope(monkeypatch):
    """The client records each call against the scope active when it was made."""
    client = github_client.GitHubClient()
    monkeypatch.setattr(
        client.session,
        "request",
        Mock(side_effect=[_response(payload={"ok": 1}), _response(payload=_graphql_payload(cost=4, remaining=4100))]),
    )

    with usage_scope(org="acme", dataset="issues"):
        client.get("https://api.github.com/x")
        client.graphql("query {}", {})

    summary = client.usage.summary()

    assert summary["orgs"]["acme"]["datasets"]["issues"] == {
        "rest_requests": 1,
        "graphql_requests": 1,
        "graphql_points": 4,
    }
    assert summary["graphql_remaining"] == 4100


def test_client_counts_every_attempt_including_retries(monkeypatch, mock_sleep):
    """A retried request spent budget each time it reached GitHub."""
    client = github_client.GitHubClient()
    monkeypatch.setattr(
        client.session,
        "request",
        Mock(side_effect=[_response(status=502), _response(status=502), _response(payload={"ok": 1})]),
    )

    with usage_scope(org="acme"):
        client.get("https://api.github.com/x")

    assert client.usage.summary()["total"]["rest_requests"] == 3
    # The pre-existing logical-call counter is unchanged by this feature.
    assert client.requests_made == 1


def test_client_does_not_count_requests_that_never_got_a_response(monkeypatch, mock_sleep):
    """A connection error produced no response, so it is not counted."""
    client = github_client.GitHubClient()
    monkeypatch.setattr(
        client.session,
        "request",
        Mock(side_effect=[requests.ConnectionError("down"), _response(payload={"ok": 1})]),
    )

    client.get("https://api.github.com/x")

    assert client.usage.summary()["total"]["rest_requests"] == 1


def test_client_keeps_legacy_cost_counter_in_step_with_the_ledger(monkeypatch):
    """``cost_used`` and the ledger agree on GraphQL points."""
    client = github_client.GitHubClient()
    monkeypatch.setattr(client.session, "request", Mock(return_value=_response(payload=_graphql_payload(cost=6))))

    client.graphql("query {}", {})
    client.graphql("query {}", {})

    assert client.cost_used == 12
    assert client.usage.summary()["total"]["graphql_points"] == 12


def test_graphql_response_without_rate_limit_block_counts_the_request_only(monkeypatch):
    """No rateLimit in the payload means no points, but the request still counts."""
    client = github_client.GitHubClient()
    monkeypatch.setattr(client.session, "request", Mock(return_value=_response(payload={"data": {}})))

    client.graphql("query {}", {})

    summary = client.usage.summary()
    assert summary["total"] == {"rest_requests": 0, "graphql_requests": 1, "graphql_points": 0}
    assert summary["graphql_remaining"] is None


# ---------------------------------------------------------
# THREAD PROPAGATION
# ---------------------------------------------------------


def test_worker_threads_inherit_the_callers_scope():
    """Pool workers must see the scope set by the thread that fanned out."""
    seen: list[UsageScope] = []
    lock = threading.Lock()

    def per_item(_item: object) -> list:
        with lock:
            seen.append(current_scope())
        return [1]

    with usage_scope(org="acme", dataset="issues"):
        fetch_all_with_retry(list(range(6)), 3, per_item, "things")

    assert seen == [UsageScope("acme", "issues")] * 6


def test_worker_requests_are_attributed_not_lost(monkeypatch):
    """End to end: requests made inside pool workers land under the org."""
    client = github_client.GitHubClient()
    monkeypatch.setattr(client.session, "request", Mock(return_value=_response(payload={"ok": 1})))

    def per_item(_item: object) -> list:
        client.get("https://api.github.com/x")
        return [1]

    with usage_scope(org="acme", dataset="issues"):
        fetch_all_with_retry(list(range(5)), 3, per_item, "things")

    summary = client.usage.summary()
    assert summary["orgs"]["acme"]["datasets"]["issues"]["rest_requests"] == 5
    assert UNATTRIBUTED not in summary["orgs"]


def test_retry_pass_after_a_failure_keeps_the_scope():
    """The reduced-concurrency retry pass also runs in the caller's scope."""
    attempts: dict[int, int] = {}
    scopes: list[UsageScope] = []

    def per_item(item: int) -> list:
        attempts[item] = attempts.get(item, 0) + 1
        scopes.append(current_scope())
        if item == 0 and attempts[item] == 1:
            raise RuntimeError("transient")
        return [item]

    with usage_scope(org="acme", dataset="prs"):
        fetch_all_with_retry([0, 1], 2, per_item, "things")

    assert attempts[0] == 2
    assert set(scopes) == {UsageScope("acme", "prs")}


# ---------------------------------------------------------
# ENTRY POINTS
# ---------------------------------------------------------


def test_fetch_org_incremental_scopes_its_fetches(monkeypatch, tmp_path):
    """Both the full and the delta fetch run under (org, resource name)."""
    monkeypatch.setattr(paths, "DATASETS_DIR", tmp_path)
    resource = OrgIncrementalResource(
        name="scoped_events",
        model_class=IssueTimelineEventRecord,
        key_of=lambda e: (e.repo, e.issue_number, e.occurred_at),
        updated_at_of=lambda e: e.occurred_at,
        task_desc="scoped events",
    )
    event = IssueTimelineEventRecord(
        repo="org/repo",
        issue_number=1,
        event_type="labeled",
        occurred_at=datetime.now(UTC),
        label="bug",
        actor="alice",
    )
    seen: list[UsageScope] = []

    def full() -> list:
        seen.append(current_scope())
        return [event]

    def since(_when: datetime) -> list:
        seen.append(current_scope())
        return []

    fetch_org_incremental(resource, org="acme", full_fetch=full, since_fetch=since)
    fetch_org_incremental(resource, org="acme", full_fetch=full, since_fetch=since)

    assert seen == [UsageScope("acme", "scoped_events")] * 2
    assert current_scope() == UsageScope(None, None)


def test_load_or_fetch_scopes_a_cold_fetch(monkeypatch, tmp_path):
    """A fetch triggered by a missing dataset is attributed to (org, resource)."""
    monkeypatch.setattr(paths, "DATASETS_DIR", tmp_path)
    seen: list[UsageScope] = []

    def fetch() -> list:
        seen.append(current_scope())
        return []

    load_or_fetch("contributor_activity", "acme", IssueTimelineEventRecord, fetch)

    assert seen == [UsageScope("acme", "contributor_activity")]


# ---------------------------------------------------------
# MARKDOWN RENDERING
# ---------------------------------------------------------


def test_render_markdown_lists_totals_orgs_and_datasets():
    """The job summary shows the run total plus per-org and per-dataset rows."""
    from hiero_analytics.data_sources.usage import render_usage_markdown

    ledger = UsageLedger()
    with usage_scope(org="acme", dataset="issues"):
        ledger.record_request(graphql=True)
        ledger.record_graphql_rate_limit(cost=3, remaining=4000)

    text = render_usage_markdown(ledger.summary())

    assert "GraphQL points spent: **3**" in text
    assert "remaining at last response: **4000**" in text
    assert "| acme | 0 | 1 | 3 |" in text
    assert "| acme | issues | 0 | 1 | 3 |" in text


def test_render_markdown_for_a_run_with_no_requests():
    """Zero usage is stated plainly, with no empty tables."""
    from hiero_analytics.data_sources.usage import render_usage_markdown

    text = render_usage_markdown(UsageLedger().summary())

    assert "No GitHub API requests were made" in text
    assert "|" not in text
    assert "remaining at last response: **n/a**" in text


def test_render_markdown_escapes_pipes_in_names():
    """A stray pipe in a name must not break the table."""
    from hiero_analytics.data_sources.usage import render_usage_markdown

    ledger = UsageLedger()
    with usage_scope(org="a|b", dataset="c|d"):
        ledger.record_request(graphql=False)

    assert "a\\|b" in render_usage_markdown(ledger.summary())
