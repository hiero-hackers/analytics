"""Process-wide adaptive concurrency limiter for GitHub API requests.

Caps how many requests may be in flight at once and shrinks that cap when GitHub
returns a secondary-rate-limit (403), recovering gradually as clean responses come
back. A single shared instance is used by every ``GitHubClient`` in a run, so a
throttle one fetch discovers slows all the others — instead of each pipeline
rediscovering the limit from scratch and re-tripping the 403.

Additive-increase / multiplicative-decrease (AIMD), the classic congestion-control
shape: halve the cap on a throttle, nudge it up by one after a streak of successes.
With no throttles it stays pinned at ``max_concurrency`` and adds no blocking.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Clean responses required before nudging the cap back up by one.
_GROW_AFTER = 20


class AdaptiveConcurrencyLimiter:
    """Bounds in-flight requests; AIMD-resizes the bound on throttle/success."""

    def __init__(self, max_concurrency: int, *, min_concurrency: int = 1) -> None:
        """Start at ``max_concurrency`` permits; never shrink below ``min_concurrency``."""
        self._max = max(1, max_concurrency)
        self._min = max(1, min(min_concurrency, self._max))
        self._limit = self._max
        self._in_flight = 0
        self._streak = 0
        self._cond = threading.Condition()

    @property
    def limit(self) -> int:
        """The current concurrency cap."""
        with self._cond:
            return self._limit

    @property
    def in_flight(self) -> int:
        """Requests currently holding a slot."""
        with self._cond:
            return self._in_flight

    @contextmanager
    def slot(self) -> Iterator[None]:
        """Block until a slot is free, hold it for the body, then release it."""
        with self._cond:
            while self._in_flight >= self._limit:
                self._cond.wait()
            self._in_flight += 1
        try:
            yield
        finally:
            with self._cond:
                self._in_flight -= 1
                self._cond.notify()

    def on_throttle(self) -> None:
        """Secondary-rate-limit signal: halve the cap, down to the floor."""
        with self._cond:
            self._streak = 0
            new_limit = max(self._min, self._limit // 2)
            if new_limit != self._limit:
                logger.info("Throttled — reducing request concurrency %d -> %d", self._limit, new_limit)
                self._limit = new_limit

    def on_success(self) -> None:
        """Clean response: nudge the cap back up after a streak of successes."""
        with self._cond:
            if self._limit >= self._max:
                self._streak = 0
                return
            self._streak += 1
            if self._streak >= _GROW_AFTER:
                self._streak = 0
                self._limit += 1
                self._cond.notify()
                logger.info("Recovered — increasing request concurrency to %d", self._limit)
