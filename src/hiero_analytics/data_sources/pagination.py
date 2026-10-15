"""
Generic pagination helpers for APIs.

Supports:
• Page-number pagination
• Cursor-based pagination (GraphQL style)

Adds optional logging and safety guards so long-running
pagination loops remain observable and debuggable.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from hiero_analytics.config.github import GITHUB_GRAPHQL_MIN_PAGE_SIZE, GITHUB_GRAPHQL_PAGE_SIZE

from .github_client import GitHubServerError

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 100

# After a shrink, this many consecutive clean pages (or rounds) double the page
# size again, up to the size it started at, so one transient 502 does not pin a
# repository at a tiny page for the rest of its history.
_RECOVERY_CLEAN_PAGES = 3


class PageSizePolicy:
    """Shrink-on-server-error, recover-on-success page size for GraphQL pagination.

    GitHub answers a query that runs too long with a 502/504, and the cure is to
    ask for fewer nodes. ``shrink`` halves the size (never below the floor);
    ``record_success`` doubles it back, up to the starting size, after
    ``_RECOVERY_CLEAN_PAGES`` consecutive successes. The reduced size persists
    between calls, so the loop that owns the policy keeps using it for the pages
    that follow.

    Shared by the per-repo cursor loop (:func:`paginate_cursor`) and the batched
    round loop so the arithmetic lives in one place.
    """

    def __init__(
        self,
        page_size: int = GITHUB_GRAPHQL_PAGE_SIZE,
        min_page_size: int = GITHUB_GRAPHQL_MIN_PAGE_SIZE,
    ) -> None:
        """Start at ``page_size``; never shrink below ``min_page_size`` (capped at ``page_size``)."""
        self.ceiling = max(1, page_size)
        self.floor = max(1, min(min_page_size, self.ceiling))
        self.current = self.ceiling
        self._clean = 0

    def shrink(self) -> bool:
        """Halve the page size after a server error; return False when already at the floor."""
        if self.current <= self.floor:
            return False
        reduced = max(self.floor, self.current // 2)
        logger.warning(
            "GitHub server error; reducing GraphQL page size from %d to %d and retrying",
            self.current,
            reduced,
        )
        self.current = reduced
        self._clean = 0
        return True

    def record_success(self) -> None:
        """Count a successful page; double the size back up after enough in a row."""
        if self.current >= self.ceiling:
            return
        self._clean += 1
        if self._clean >= _RECOVERY_CLEAN_PAGES:
            self.current = min(self.ceiling, self.current * 2)
            self._clean = 0
            logger.info("GraphQL page size recovering to %d", self.current)


# --------------------------------------------------------
# PAGE NUMBER PAGINATION
# --------------------------------------------------------


def paginate_cursor(
    fetch_page: Callable[[str | None, int], tuple[list[Any], str | None, bool]],
    max_pages: int | None = None,
    *,
    page_size: int = GITHUB_GRAPHQL_PAGE_SIZE,
    min_page_size: int = GITHUB_GRAPHQL_MIN_PAGE_SIZE,
) -> list[Any]:
    """
    Generic paginator for cursor-based APIs such as GraphQL.

    fetch_page(cursor, page_size) must return:
        (items, next_cursor, has_next_page)

    When ``fetch_page`` raises :class:`GitHubServerError` (GitHub's 502/504 for a
    query that ran too long) the page size is halved, never below
    ``min_page_size``, and the same cursor is retried; at the floor the error is
    re-raised. The reduced size persists for the following pages and doubles back
    after a few clean ones (see :class:`PageSizePolicy`).

    Parameters
    ----------
    fetch_page:
        Function that retrieves a single page of at most ``page_size`` items.

    max_pages:
        Optional debugging guard to stop runaway pagination.

    page_size:
        Nodes to request per page, and the size recovery grows back to.

    min_page_size:
        Smallest page to try before giving up on a server error.
    """
    policy = PageSizePolicy(page_size, min_page_size)
    results: list[Any] = []
    cursor: str | None = None
    page = 1

    logger.debug(
        "Requesting cursor pages (start_page=%d, start_cursor=%s)",
        page,
        cursor,
    )

    while True:
        logger.debug(
            "Requesting cursor page %d (cursor=%s)",
            page,
            cursor,
        )

        try:
            items, next_cursor, has_next = fetch_page(cursor, policy.current)
        except GitHubServerError:
            if not policy.shrink():
                raise
            continue
        policy.record_success()

        logger.debug(
            "Cursor page %d returned %d items (has_next=%s)",
            page,
            len(items),
            has_next,
        )

        results.extend(items)

        if not has_next:
            logger.debug("Cursor pagination complete")
            break

        cursor = next_cursor
        page += 1

        if max_pages is not None and page > max_pages:
            logger.warning(
                "Cursor pagination stopped after max_pages=%d",
                max_pages,
            )
            break

    logger.info("Cursor pagination collected %d items total", len(results))

    return results


# ---------------------------------------------------------
# GRAPHQL CURSOR PAGE EXTRACTION
# ---------------------------------------------------------


def extract_graphql_cursor_page(
    data: dict[str, Any],
    nodes_path: list[str],
) -> tuple[list[dict[str, Any]], str | None, bool]:
    """Safely navigates a GraphQL response and extracts nodes + pagination info."""
    container = data.get("data", {})
    for key in nodes_path:
        if not isinstance(container, dict):
            logger.warning("Path traversal failed: '%s' is not a dict.", key)
            return [], None, False
        container = container.get(key, {})

    if not isinstance(container, dict):
        return [], None, False

    nodes = container.get("nodes")
    if nodes is None:
        nodes = [container] if container else []

    if not isinstance(nodes, list):
        logger.error("Expected list at %s, got %s", nodes_path, type(nodes))
        nodes = []

    page_info = container.get("pageInfo", {})
    if not isinstance(page_info, dict):
        page_info = {}
    next_cursor = page_info.get("endCursor")
    has_next = bool(page_info.get("hasNextPage", False))

    return nodes, next_cursor, has_next
