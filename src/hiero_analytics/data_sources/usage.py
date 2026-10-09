"""GitHub API usage attribution.

Answers "what does each organisation cost in API budget?" without threading an
org argument through every fetch function. Callers tag the work they are about
to do with :func:`usage_scope`; the client then records every request against
whatever scope is current on the calling thread.

The scope lives in a :class:`~contextvars.ContextVar`, so it is private to the
logical flow of control that set it. Threads do **not** inherit a context on
their own — code that fans work out to a pool must submit it through
``contextvars.copy_context().run`` (see ``github_ingest._common``), otherwise
worker requests land in the ``unattributed`` bucket.

This module only counts. It never sleeps, retries, or changes rate-limit
behaviour; that stays in ``github_client`` and ``rate_limit``.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, NamedTuple

# Bucket name for requests made outside any scope (or inside a scope that set
# no org / no dataset). Surfacing it, rather than dropping the requests, keeps
# the per-org rows honest: whatever they do not explain is visible.
UNATTRIBUTED = "unattributed"


class UsageScope(NamedTuple):
    """Who a request is being made on behalf of.

    ``dataset`` names the persisted dataset being fetched, or the pipeline when
    the work is not part of a dataset (the finer label wins when both apply).
    """

    org: str | None = None
    dataset: str | None = None


_scope: ContextVar[UsageScope | None] = ContextVar("github_usage_scope", default=None)


def current_scope() -> UsageScope:
    """The scope requests made right now will be attributed to."""
    scope = _scope.get()
    return scope if scope is not None else UsageScope()


@contextmanager
def usage_scope(*, org: str | None = None, dataset: str | None = None) -> Iterator[UsageScope]:
    """Attribute requests made inside the block to ``org`` / ``dataset``.

    Fields left as ``None`` inherit from the enclosing scope, so a pipeline can
    set the org once and each dataset fetch beneath it only names the dataset.
    """
    outer = current_scope()
    inner = UsageScope(
        org=org if org is not None else outer.org,
        dataset=dataset if dataset is not None else outer.dataset,
    )
    token = _scope.set(inner)
    try:
        yield inner
    finally:
        _scope.reset(token)


@dataclass
class UsageTotals:
    """Counters for one scope (or a rollup of several)."""

    rest_requests: int = 0
    graphql_requests: int = 0
    graphql_points: int = 0

    def add(self, other: UsageTotals) -> None:
        """Accumulate ``other`` into this instance."""
        self.rest_requests += other.rest_requests
        self.graphql_requests += other.graphql_requests
        self.graphql_points += other.graphql_points

    def to_dict(self) -> dict[str, int]:
        """Plain-dict form for JSON."""
        return {
            "rest_requests": self.rest_requests,
            "graphql_requests": self.graphql_requests,
            "graphql_points": self.graphql_points,
        }


class UsageLedger:
    """Thread-safe record of API usage, keyed by :class:`UsageScope`."""

    def __init__(self) -> None:
        """Start empty."""
        self._lock = threading.Lock()
        self._by_scope: dict[UsageScope, UsageTotals] = {}
        self._graphql_remaining: int | None = None

    def _totals(self, scope: UsageScope) -> UsageTotals:
        """Totals for ``scope``, created on first use. Caller holds the lock."""
        totals = self._by_scope.get(scope)
        if totals is None:
            totals = self._by_scope[scope] = UsageTotals()
        return totals

    def record_request(self, *, graphql: bool) -> None:
        """Count one HTTP response against the current scope.

        Called once per response the transport receives, so a retried request
        counts each time it reached GitHub. A request that never got a response
        (connection error, timeout) is not counted: nothing confirms it spent
        budget.
        """
        scope = current_scope()
        with self._lock:
            totals = self._totals(scope)
            if graphql:
                totals.graphql_requests += 1
            else:
                totals.rest_requests += 1

    def record_graphql_rate_limit(self, *, cost: object, remaining: object) -> None:
        """Record the ``rateLimit`` block of a GraphQL response.

        ``cost`` is added to the current scope; ``remaining`` replaces the last
        observed value. Non-integer values (a malformed payload) are ignored
        rather than allowed to corrupt the totals.
        """
        scope = current_scope()
        with self._lock:
            if _is_count(cost):
                self._totals(scope).graphql_points += cost  # type: ignore[operator]
            if _is_count(remaining):
                self._graphql_remaining = remaining  # type: ignore[assignment]

    def reset(self) -> None:
        """Forget everything — called at the start of each run."""
        with self._lock:
            self._by_scope.clear()
            self._graphql_remaining = None

    def summary(self) -> dict[str, Any]:
        """JSON-ready rollup: run total, per-org totals, and per-dataset detail.

        ``graphql_remaining`` is the budget GitHub last reported. Under
        concurrent workers "last" is approximate; it is a gauge of how close the
        run came to the limit, not an exact figure.
        """
        with self._lock:
            entries = {scope: UsageTotals(**totals.to_dict()) for scope, totals in self._by_scope.items()}
            remaining = self._graphql_remaining

        total = UsageTotals()
        orgs: dict[str, dict[str, Any]] = {}
        for scope in sorted(entries, key=lambda s: (s.org or UNATTRIBUTED, s.dataset or UNATTRIBUTED)):
            totals = entries[scope]
            total.add(totals)
            org_entry = orgs.setdefault(
                scope.org or UNATTRIBUTED,
                {**UsageTotals().to_dict(), "datasets": {}},
            )
            org_rollup = UsageTotals(
                org_entry["rest_requests"],
                org_entry["graphql_requests"],
                org_entry["graphql_points"],
            )
            org_rollup.add(totals)
            org_entry.update(org_rollup.to_dict())
            dataset_name = scope.dataset or UNATTRIBUTED
            dataset_entry = org_entry["datasets"].setdefault(dataset_name, UsageTotals())
            dataset_entry.add(totals)

        for org_entry in orgs.values():
            org_entry["datasets"] = {name: totals.to_dict() for name, totals in org_entry["datasets"].items()}

        return {
            "total": total.to_dict(),
            "graphql_remaining": remaining,
            "orgs": orgs,
        }


def _is_count(value: object) -> bool:
    """True for a real integer count (``bool`` is excluded: it is an ``int``)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _cell(value: object) -> str:
    """Escape a value for a Markdown table cell."""
    return str(value).replace("|", "\\|")


def _row(*cells: object) -> str:
    return "| " + " | ".join(_cell(cell) for cell in cells) + " |"


def render_usage_markdown(api_usage: dict[str, Any]) -> str:
    """Render a :meth:`UsageLedger.summary` dict as Markdown tables.

    Takes the same dict that is written to ``SNAPSHOT.json`` under
    ``api_usage``, so the job summary and the archived manifest cannot disagree.
    """
    total = api_usage["total"]
    remaining = api_usage.get("graphql_remaining")
    orgs: dict[str, dict[str, Any]] = api_usage.get("orgs", {})

    lines = [
        "## GitHub API usage",
        "",
        f"- REST requests: **{total['rest_requests']}**",
        f"- GraphQL requests: **{total['graphql_requests']}**",
        f"- GraphQL points spent: **{total['graphql_points']}**",
        f"- GraphQL points remaining at last response: **{remaining if remaining is not None else 'n/a'}**",
        "",
    ]
    if not orgs:
        lines.append("No GitHub API requests were made in this run.")
        return "\n".join(lines) + "\n"

    header = ("REST requests", "GraphQL requests", "GraphQL points")
    lines += ["### By organisation", "", _row("Organisation", *header), _row("---", "---:", "---:", "---:")]
    for org, entry in orgs.items():
        lines.append(_row(org, entry["rest_requests"], entry["graphql_requests"], entry["graphql_points"]))

    lines += ["", "### By organisation and dataset", "", _row("Organisation", "Dataset", *header)]
    lines.append(_row("---", "---", "---:", "---:", "---:"))
    for org, entry in orgs.items():
        for dataset, counts in entry["datasets"].items():
            lines.append(
                _row(org, dataset, counts["rest_requests"], counts["graphql_requests"], counts["graphql_points"])
            )
    return "\n".join(lines) + "\n"
