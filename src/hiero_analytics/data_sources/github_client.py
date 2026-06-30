"""
Low-level GitHub HTTP client.

Handles authentication, connection reuse, retries, and request execution
for both REST and GraphQL API calls.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Mapping
from typing import Any

import requests

from hiero_analytics.config.github import (
    BASE_URL,
    GITHUB_MAX_WORKERS,
    GITHUB_TOKEN,
    HTTP_TIMEOUT_SECONDS,
    REQUEST_DELAY_SECONDS,
    SECONDARY_RATE_LIMIT_FALLBACK_SECONDS,
)

from .adaptive_limiter import AdaptiveConcurrencyLimiter
from .rate_limit import (
    JSON,
    Action,
    RateLimitDecision,
    RateLimitPolicy,
    RateLimitSnapshot,
)

logger = logging.getLogger(__name__)

# One shared limiter for the whole process, so every GitHubClient (and every
# pipeline in run_all) throttles together when GitHub starts returning
# secondary-rate-limit 403s, and recovers together afterwards.
_LIMITER = AdaptiveConcurrencyLimiter(GITHUB_MAX_WORKERS)

MAX_RETRIES = 3
MAX_GRAPHQL_FRESH_RETRIES = 2
RETRY_STATUS_CODES = {500, 502, 503, 504}

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
        # Thread lock to protect usage counters during concurrent execution.
        self._lock = threading.Lock()

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
        with self._lock:
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
                with _LIMITER.slot():
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
            if response.status_code in RETRY_STATUS_CODES:
                if attempt == MAX_RETRIES:
                    logger.error(
                        "Server error %d after %d attempts",
                        response.status_code,
                        MAX_RETRIES,
                    )
                    response.raise_for_status()

                sleep_time = (2 ** attempt) + random.uniform(0, 1) # small jitter
                logger.warning(
                    "Server error %d. Retrying in %.2fs...",
                    response.status_code,
                    sleep_time,
                )
                time.sleep(sleep_time)
                continue

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
                    logger.info("Retrying due to REST rate limit...")
                    continue

            if response.status_code == 403 and attempt < MAX_RETRIES:
                retry_after = response.headers.get("Retry-After")
                message = ""
                if retry_after is None:
                    try:
                        payload = response.json()
                        if isinstance(payload, dict):
                            message = str(payload.get("message", ""))
                    except ValueError:
                        message = ""
                is_rate_limited = "rate limit" in message.lower()

                if retry_after is not None or is_rate_limited:
                    _LIMITER.on_throttle()  # shrink request concurrency for the whole run
                    if retry_after is not None and retry_after.isdigit():
                        sleep_seconds = max(int(retry_after), 1)
                    else:
                        sleep_seconds = SECONDARY_RATE_LIMIT_FALLBACK_SECONDS
                    logger.warning(
                        "Secondary rate limit hit (403). Sleeping %ds before retry %d.",
                        sleep_seconds,
                        attempt + 1,
                    )
                    time.sleep(sleep_seconds)
                    continue
                
            response.raise_for_status()
            _LIMITER.on_success()  # clean response — let concurrency recover over time
            return response

        raise RuntimeError("Unreachable request state")


    def _request(self, method: str, url: str, **kwargs: Any) -> JSON:
        """
        Execute request and apply GraphQL-specific retry policy.
        """
        is_graphql = url.endswith("/graphql")

        start_time = time.time()
        MAX_TOTAL_TIME = 60  # seconds

        for attempt in range(1, MAX_GRAPHQL_FRESH_RETRIES + 2):
            if time.time() - start_time > MAX_TOTAL_TIME:
                raise TimeoutError("GraphQL request exceeded total retry time")
        
            response = self._execute_http_with_retries(method, url, **kwargs)
            data: JSON = response.json()

            # Keep usage accounting for both REST and GraphQL.
            graphql_snapshot = self._record_usage(data, is_graphql=is_graphql)

            if not is_graphql:
                if REQUEST_DELAY_SECONDS > 0:
                    time.sleep(REQUEST_DELAY_SECONDS)
                return data

            error_decision = self._policy.check_graphql_errors(data, graphql_snapshot)
            if "errors" in data:
                logger.warning(
                    "GraphQL errors (attempt %d): %s",
                     attempt, 
                     data["errors"],
                     )
            action = self._apply_decision(error_decision)

            if action == Action.DELAY_THEN_RETRY_FRESH:
                logger.info("GraphQL retry attempt %d", attempt)
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
