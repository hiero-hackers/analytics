"""Tests for the pure rate-limit policy: snapshot parsing and back-off decisions.

The policy makes no HTTP calls and never sleeps — it only reads a normalized
snapshot and returns an Action. These tests pin the decision tree directly,
rather than through the GitHubClient loop that applies it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hiero_analytics.data_sources.rate_limit import (
    Action,
    RateLimitPolicy,
    RateLimitSnapshot,
)

# -- snapshot construction ----------------------------------------------------


def test_snapshot_from_rest_headers_parses_budget_and_reset():
    """X-RateLimit-* headers become a normalized snapshot with an aware reset time."""
    snap = RateLimitSnapshot.from_rest_headers(
        {"X-RateLimit-Remaining": "12", "X-RateLimit-Limit": "5000", "X-RateLimit-Reset": "1893456000"}
    )
    assert snap is not None
    assert snap.remaining == 12
    assert snap.limit == 5000
    assert snap.reset_at == datetime.fromtimestamp(1893456000, tz=UTC)


def test_snapshot_from_rest_headers_absent_returns_none():
    """Endpoints that send no rate-limit headers yield no snapshot."""
    assert RateLimitSnapshot.from_rest_headers({}) is None


def test_snapshot_from_rest_headers_malformed_returns_none():
    """Non-integer header values are a missing snapshot, not a crash."""
    assert RateLimitSnapshot.from_rest_headers({"X-RateLimit-Remaining": "not-a-number"}) is None


def test_snapshot_from_rest_headers_out_of_range_reset_returns_none():
    """A reset epoch beyond the platform range is a missing snapshot, not a crash."""
    assert RateLimitSnapshot.from_rest_headers({"X-RateLimit-Reset": "99999999999999999"}) is None


def test_snapshot_from_graphql_payload_reads_ratelimit_block():
    """A GraphQL rateLimit block becomes a snapshot including query cost."""
    snap = RateLimitSnapshot.from_graphql_payload(
        {"data": {"rateLimit": {"remaining": 100, "limit": 5000, "cost": 3, "resetAt": "2030-01-01T00:00:00Z"}}}
    )
    assert snap is not None
    assert (snap.remaining, snap.limit, snap.cost) == (100, 5000, 3)


def test_snapshot_from_graphql_payload_without_ratelimit_returns_none():
    """A query that didn't request rateLimit yields no snapshot."""
    assert RateLimitSnapshot.from_graphql_payload({"data": {"viewer": {"login": "x"}}}) is None


def test_snapshot_from_graphql_payload_with_malformed_shape_returns_none():
    """A non-mapping data or rateLimit block is ignored instead of raising."""
    assert RateLimitSnapshot.from_graphql_payload({"data": {"rateLimit": "throttled"}}) is None
    assert RateLimitSnapshot.from_graphql_payload({"data": "unavailable"}) is None


def test_seconds_until_reset_never_negative():
    """A reset time in the past reports zero seconds remaining, not a negative."""
    past = RateLimitSnapshot(reset_at=datetime.now(UTC) - timedelta(hours=1))
    assert past.seconds_until_reset() == 0
    assert RateLimitSnapshot(reset_at=None).seconds_until_reset() == 0


# -- REST decision tree -------------------------------------------------------


def test_rest_proceeds_when_budget_remains():
    """Budget above zero proceeds with no delay."""
    decision = RateLimitPolicy().check_rest_response(
        RateLimitSnapshot(remaining=10), status_code=200, is_ok=True, attempt=1, max_retries=3
    )
    assert decision.action is Action.PROCEED


def test_rest_no_headers_proceeds():
    """A snapshot with no remaining count carries no signal -> proceed."""
    decision = RateLimitPolicy().check_rest_response(
        RateLimitSnapshot(remaining=None), status_code=200, is_ok=True, attempt=1, max_retries=3
    )
    assert decision.action is Action.PROCEED


def test_rest_403_at_zero_budget_retries_the_loop():
    """A 403 with exhausted budget sleeps until reset, then retries the same request."""
    reset = datetime.now(UTC) + timedelta(seconds=120)
    decision = RateLimitPolicy().check_rest_response(
        RateLimitSnapshot(remaining=0, reset_at=reset), status_code=403, is_ok=False, attempt=1, max_retries=3
    )
    assert decision.action is Action.DELAY_THEN_RETRY_LOOP
    assert decision.sleep_seconds > 0


def test_rest_200_at_zero_budget_delays_then_returns():
    """A successful response that exhausted the budget sleeps as a courtesy, then returns."""
    reset = datetime.now(UTC) + timedelta(seconds=90)
    decision = RateLimitPolicy().check_rest_response(
        RateLimitSnapshot(remaining=0, reset_at=reset), status_code=200, is_ok=True, attempt=1, max_retries=3
    )
    assert decision.action is Action.DELAY_THEN_PROCEED
    assert decision.sleep_seconds > 0


# -- GraphQL budget + errors --------------------------------------------------


def test_graphql_low_budget_backs_off():
    """A critically low GraphQL point budget triggers a short proactive pause."""
    decision = RateLimitPolicy().check_graphql_budget(RateLimitSnapshot(remaining=10))
    assert decision.action is Action.DELAY_THEN_PROCEED
    assert decision.sleep_seconds > 0


def test_graphql_healthy_budget_proceeds():
    """Ample GraphQL budget proceeds without delay."""
    assert RateLimitPolicy().check_graphql_budget(RateLimitSnapshot(remaining=500)).action is Action.PROCEED


def test_graphql_rate_limit_error_retries_fresh():
    """A RATE_LIMIT error sleeps (>= the floor) and restarts the request fresh."""
    data = {"errors": [{"type": "RATE_LIMIT", "message": "exhausted"}]}
    decision = RateLimitPolicy().check_graphql_errors(data, snapshot=None)
    assert decision.action is Action.DELAY_THEN_RETRY_FRESH
    assert decision.sleep_seconds >= 60


def test_graphql_non_rate_limit_error_raises():
    """A non-rate-limit GraphQL error is not retriable — it raises immediately."""
    data = {"errors": [{"type": "NOT_FOUND", "message": "no such repo"}]}
    with pytest.raises(RuntimeError, match="GraphQL error"):
        RateLimitPolicy().check_graphql_errors(data, snapshot=None)


def test_graphql_no_errors_proceeds():
    """A clean GraphQL payload proceeds."""
    assert RateLimitPolicy().check_graphql_errors({"data": {}}, snapshot=None).action is Action.PROCEED
