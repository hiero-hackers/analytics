"""
Low-level GitHub HTTP client.

Handles authentication, connection reuse, retries, and request execution
for both REST and GraphQL API calls.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import Any

import requests

from hiero_analytics.config.github import (
    BASE_URL,
    GITHUB_TOKEN,
    HTTP_TIMEOUT_SECONDS,
    REQUEST_DELAY_SECONDS,
)
from .rate_limit import (
    Action,
    JSON,
    RateLimitDecision,
    RateLimitPolicy,
    RateLimitSnapshot,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
MAX_GRAPHQL_FRESH_RETRIES = 2

# --------------------------------------------------------
# HEADERS
# --------------------------------------------------------

def github_headers() -> dict[str, str]:
    """Build HTTP headers required for GitHub API requests."""
    headers: dict[str, str] = {
        "User-Agent": "hiero-analytics",
        "Accept": "application/vnd.github+json",
    }

    if not GITHUB_TOKEN:
        logger.warning(
            "GITHUB_TOKEN not set. Unauthenticated rate limit is 60 requests/hour."
        )
        return headers

    logger.info(
        "Using GITHUB_TOKEN for authenticated requests. "
        "API allows up to 5000 requests per hour."
    )
    headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


# --------------------------------------------------------
# CLIENT
# --------------------------------------------------------

class GitHubClient:
    """HTTP client for interacting with the GitHub API."""

    def __init__(self) -> None:
        self.session: requests.Session = requests.Session()
        self.session.headers.update(github_headers())

        # Rate-limit policy: reads signals, returns decisions.
        self._policy = RateLimitPolicy()

        # usage counters to keep track of API usage
        self.requests_made: int = 0
        self.cost_used: int = 0

    # --------------------------------------------------------
    # USAGE REPORTING
    # --------------------------------------------------------

    def log_usage(self) -> None:
        """Log cumulative API usage statistics."""
        logger.info(
            "GitHub API usage: %d requests, %d GraphQL points used",
            self.requests_made,
            self.cost_used,
        )

    def _apply_decision(self, decision: RateLimitDecision) -> Action:
        """Apply policy decision side effects and return the action."""
        if decision.sleep_seconds > 0:
            time.sleep(decision.sleep_seconds)
        return decision.action

    def _record_usage(
        self,
        data: JSON,
        *,
        is_graphql: bool,
    ) -> RateLimitSnapshot | None:
        """Extract rate-limit info from response and update usage counters."""
        self.requests_made += 1
        if not is_graphql:
            return None

        snapshot = RateLimitSnapshot.from_graphql_payload(data)
        if snapshot and snapshot.cost is not None:
            self.cost_used += snapshot.cost
        return snapshot

    # --------------------------------------------------------
    # REQUEST EXECUTION
    # --------------------------------------------------------

    def _execute_http_with_retries(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> requests.Response:
        """
        Handle low-level network retries and REST header-based rate limiting.
        Returns a successful HTTP response or raises.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            logger.debug(
                "GitHub request -> %s %s (attempt %d)",
                method,
                url,
                attempt,
            )
            start = time.time()

            try:
                response = self.session.request(
                    method,
                    url,
                    timeout=HTTP_TIMEOUT_SECONDS,
                    **kwargs,
                )
            except requests.RequestException as exc:
                if attempt == MAX_RETRIES:
                    logger.error(
                        "GitHub request failed after %d attempts",
                        MAX_RETRIES,
                    )
                    raise
                logger.warning(
                    "Request error (%s). Retrying attempt %d...",
                    exc,
                    attempt + 1,
                )
                time.sleep(2 ** attempt)
                continue

            logger.debug("GitHub response <- %.2fs", time.time() - start)

            # Check REST headers for all endpoints, including GraphQL.
            snapshot = RateLimitSnapshot.from_rest_headers(response.headers)
            if snapshot:
                rest_decision = self._policy.check_rest_response(
                    snapshot,
                    status_code=response.status_code,
                    is_ok=response.ok,
                    attempt=attempt,
                    max_retries=MAX_RETRIES,
                )
                action = self._apply_decision(rest_decision)
                if action == Action.DELAY_THEN_RETRY_LOOP:
                    continue

            response.raise_for_status()
            return response

        raise RuntimeError("Unreachable request state")


    def _request(self, method: str, url: str, **kwargs: Any) -> JSON:
        """
        Execute request and apply GraphQL-specific retry policy.
        """
        is_graphql = url.endswith("/graphql")

        for _fresh_retry_count in range(MAX_GRAPHQL_FRESH_RETRIES + 1):
            response = self._execute_http_with_retries(method, url, **kwargs)
            data: JSON = response.json()

            # Keep usage accounting for both REST and GraphQL.
            graphql_snapshot = self._record_usage(data, is_graphql=is_graphql)

            if not is_graphql:
                if REQUEST_DELAY_SECONDS > 0:
                    time.sleep(REQUEST_DELAY_SECONDS)
                return data

            error_decision = self._policy.check_graphql_errors(data, graphql_snapshot)
            action = self._apply_decision(error_decision)

            if action == Action.DELAY_THEN_RETRY_FRESH:
                continue

            if graphql_snapshot:
                budget_decision = self._policy.check_graphql_budget(graphql_snapshot)
                self._apply_decision(budget_decision)

            if REQUEST_DELAY_SECONDS > 0:
                time.sleep(REQUEST_DELAY_SECONDS)

            return data

        raise RuntimeError(
            "GraphQL fresh retry limit exceeded after RATE_LIMIT responses"
        )

    # --------------------------------------------------------
    # PUBLIC API
    # --------------------------------------------------------

    def get(self, url: str, **kwargs: Any) -> JSON:
        """
        Execute a GET request to a GitHub REST endpoint.

        Args:
            url: Full GitHub API URL

        Returns:
            Parsed JSON response
        """
        return self._request("GET", url, **kwargs)

    def graphql(self, query: str, variables: Mapping[str, Any]) -> JSON:
        """
        Execute a GraphQL query against the GitHub API.

        Args:
            query: GraphQL query string
            variables: Variables passed to the query

        Returns:
            Parsed JSON response
        """
        payload: JSON = {"query": query, "variables": dict(variables)}
        return self._request("POST", f"{BASE_URL}/graphql", json=payload)