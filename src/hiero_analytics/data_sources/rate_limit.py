"""
GitHub API rate-limit policy.

Reads rate-limit signals from REST headers and GraphQL response payloads
and returns an Action decision.  No side effects: this module never sleeps
or makes HTTP calls — the GitHubClient loop does that.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)

JSON = dict[str, Any]


# --------------------------------------------------------
# NORMALIZED SNAPSHOT
# --------------------------------------------------------

@dataclass(frozen=True)
class RateLimitSnapshot:
    """
    A single, normalized view of GitHub rate-limit state.

    Built from either:
    - REST response headers  (X-RateLimit-*)
    - GraphQL response body  (data.rateLimit)

    Having one shape regardless of protocol means policy logic
    only has to be written once.
    """

    remaining: int | None = None    # requests / points left
    limit: int | None = None        # total budget per window
    cost: int | None = None         # GraphQL only: cost of this query
    reset_at: datetime | None = None  # aware UTC datetime when budget resets

    @classmethod
    def from_rest_headers(cls, headers: Mapping[str, str]) -> RateLimitSnapshot | None:
        """
        Build from X-RateLimit-* HTTP response headers.

        Returns None when the headers are absent (e.g. webhook endpoints
        or GraphQL endpoints don't send them).
        """
        raw_remaining = headers.get("X-RateLimit-Remaining")
        raw_reset = headers.get("X-RateLimit-Reset")
        raw_limit = headers.get("X-RateLimit-Limit")

        if raw_remaining is None and raw_reset is None:
            return None

        try:
            remaining = int(raw_remaining) if raw_remaining is not None else None
            reset_epoch = int(raw_reset) if raw_reset is not None else None
            limit = int(raw_limit) if raw_limit is not None else None
        except (TypeError, ValueError):
            return None

        reset_at = (
            datetime.fromtimestamp(reset_epoch, tz=timezone.utc)
            if reset_epoch is not None
            else None
        )

        return cls(remaining=remaining, limit=limit, reset_at=reset_at)

    @classmethod
    def from_graphql_payload(cls, data: JSON) -> RateLimitSnapshot | None:
        """
        Build from a GraphQL response body that includes a rateLimit field.

        Returns None when the query didn't request rateLimit.
        """
        rate = (data.get("data") or {}).get("rateLimit")
        if not rate:
            return None

        reset_at: datetime | None = None
        raw_reset = rate.get("resetAt")
        if raw_reset:
            reset_at = datetime.fromisoformat(raw_reset.replace("Z", "+00:00"))

        return cls(
            remaining=rate.get("remaining"),
            limit=rate.get("limit"),
            cost=rate.get("cost"),
            reset_at=reset_at,
        )

    def seconds_until_reset(self) -> int:
        """Seconds until the budget window resets (0 if unknown or already passed)."""
        if self.reset_at is None:
            return 0
        return max(0, int((self.reset_at - datetime.now(timezone.utc)).total_seconds()))


# --------------------------------------------------------
# DECISION
# --------------------------------------------------------

class Action(Enum):
    """What the GitHubClient loop should do after reading rate-limit signals."""

    PROCEED = auto()
    """No action needed — return the response normally."""

    DELAY_THEN_PROCEED = auto()
    """
    Sleep for `sleep_seconds`, then return the current response.
    Used when REST budget is exhausted but the response was still 200 OK.
    """

    DELAY_THEN_RETRY_LOOP = auto()
    """
    Sleep for `sleep_seconds`, then `continue` the retry loop.
    Used for REST 403 rate-limit errors where we want to retry the same request.
    """

    DELAY_THEN_RETRY_FRESH = auto()
    """
    Sleep for `sleep_seconds`, then restart the whole request (resets retries).
    Used for GraphQL RATE_LIMIT errors, which can occur independently of
    the REST quota and may require waiting a full hour.
    """


@dataclass(frozen=True)
class RateLimitDecision:
    """ A decision returned by the policy after inspecting a snapshot or response.
    The GitHubClient loop will apply the decision by sleeping and/or retrying
    as needed.
    """

    action: Action
    sleep_seconds: int = 0
    reason: str = ""


# --------------------------------------------------------
# THRESHOLDS
# --------------------------------------------------------

# GraphQL: warn and slow down when this many points remain
_GRAPHQL_LOW_BUDGET_THRESHOLD = 50
_GRAPHQL_LOW_BUDGET_SLEEP = 5

# GraphQL RATE_LIMIT error: wait at least this long even if reset_at is missing
_GRAPHQL_ERROR_FALLBACK_SLEEP = 300
# GraphQL RATE_LIMIT error: never sleep less than this even if reset_at is soon
_GRAPHQL_ERROR_MIN_SLEEP = 60


# --------------------------------------------------------
# POLICY
# --------------------------------------------------------

class RateLimitPolicy:
    """
    Pure rate-limit decision logic.

    Each method inspects a snapshot (or raw data) and returns a
    RateLimitDecision.  No sleeping, no HTTP calls, no state mutations.
    """

    def check_rest_response(
        self,
        snapshot: RateLimitSnapshot,
        *,
        status_code: int,
        is_ok: bool,
        attempt: int,
        max_retries: int,
    ) -> RateLimitDecision:
        """
        Decide what to do after reading REST rate-limit headers.

        Decision tree:
        1. Budget > 0       → PROCEED  (no sleep needed)
        2. Budget = 0 + 403 → DELAY_THEN_RETRY_LOOP  (standard retry)
        3. Budget = 0 + 200 → DELAY_THEN_PROCEED     (courtesy sleep before return)
        """
        if snapshot.remaining is None:
            return RateLimitDecision(Action.PROCEED)

        logger.debug(
            "REST rate limit: remaining=%s/%s resets in %ds",
            snapshot.remaining,
            snapshot.limit,
            snapshot.seconds_until_reset(),
        )

        if snapshot.remaining > 0:
            return RateLimitDecision(Action.PROCEED)

        # Budget is zero
        sleep_seconds = snapshot.seconds_until_reset()

        if status_code == 403 and attempt < max_retries:
            logger.warning(
                "REST rate limit hit (403). Sleeping %ds before retry %d.",
                sleep_seconds,
                attempt + 1,
            )
            return RateLimitDecision(
                Action.DELAY_THEN_RETRY_LOOP,
                sleep_seconds=sleep_seconds,
                reason="REST 403 rate-limit",
            )

        if is_ok and sleep_seconds > 0:
            logger.warning(
                "REST rate limit exhausted. Sleeping %ds before returning response.",
                sleep_seconds,
            )
            return RateLimitDecision(
                Action.DELAY_THEN_PROCEED,
                sleep_seconds=sleep_seconds,
                reason="REST budget exhausted on successful response",
            )

        return RateLimitDecision(Action.PROCEED)

    def check_graphql_budget(
        self,
        snapshot: RateLimitSnapshot,
    ) -> RateLimitDecision:
        """
        Proactive back-off when GraphQL budget is critically low.
        Called after every successful GraphQL response.
        """
        if snapshot.remaining is None:
            return RateLimitDecision(Action.PROCEED)

        logger.debug(
            "GraphQL rate limit: cost=%s remaining=%s/%s resets in %ds",
            snapshot.cost,
            snapshot.remaining,
            snapshot.limit,
            snapshot.seconds_until_reset(),
        )

        if snapshot.remaining < _GRAPHQL_LOW_BUDGET_THRESHOLD:
            logger.warning(
                "GraphQL budget low (%s remaining). Pausing %ds.",
                snapshot.remaining,
                _GRAPHQL_LOW_BUDGET_SLEEP,
            )
            return RateLimitDecision(
                Action.DELAY_THEN_PROCEED,
                sleep_seconds=_GRAPHQL_LOW_BUDGET_SLEEP,
                reason=f"GraphQL budget low ({snapshot.remaining} remaining)",
            )

        return RateLimitDecision(Action.PROCEED)

    def check_graphql_errors(
        self,
        data: JSON,
        snapshot: RateLimitSnapshot | None,
    ) -> RateLimitDecision:
        """
        Inspect GraphQL errors list.

        - RATE_LIMIT type   → DELAY_THEN_RETRY_FRESH (sleep until reset, retry fresh)
        - Any other error   → raises RuntimeError immediately (not retriable)
        - No errors         → PROCEED
        """
        errors = data.get("errors")
        if not errors:
            return RateLimitDecision(Action.PROCEED)

        for err in errors:
            if err.get("type") == "RATE_LIMIT":
                logger.warning("GraphQL RATE_LIMIT error received.")

                sleep_seconds = _GRAPHQL_ERROR_FALLBACK_SLEEP
                if snapshot and snapshot.reset_at:
                    sleep_seconds = max(
                        snapshot.seconds_until_reset(),
                        _GRAPHQL_ERROR_MIN_SLEEP,
                    )

                logger.warning(
                    "Sleeping %ds before retrying GraphQL request.",
                    sleep_seconds,
                )
                return RateLimitDecision(
                    Action.DELAY_THEN_RETRY_FRESH,
                    sleep_seconds=sleep_seconds,
                    reason="GraphQL RATE_LIMIT error",
                )

        # Non-rate-limit GraphQL errors are programming errors or server bugs.
        # Raise immediately.
        raise RuntimeError(f"GitHub GraphQL error: {data}")