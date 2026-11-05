"""Multi-night simulation of the org issues dataset against a fake GitHub (#623).

Drives the production path end to end: ``fetch_org_issues_graphql`` plans per
repository in the dataset store, fetches through the real batched engine (real
query text, aliases and cursors), and persists between nights. The fake answers
the batched issue queries the way GitHub does, including a
``RESOURCE_LIMITS_EXCEEDED`` round, and the repository lookup used before rows
are retired. The clock advances one night at a time.

Covers #623's acceptance (a) to (d): an active dataset full-refreshes on
schedule, a deleted record disappears at its repository's next full refresh, a
late-joining repository is backfilled, and a night that hits a resource error
still completes and saves.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta

import pytest

from hiero_analytics.config import paths
from hiero_analytics.data_sources import dataset_store
from hiero_analytics.data_sources.github_ingest import _common, issues
from hiero_analytics.data_sources.models import RepositoryRecord
from hiero_analytics.data_sources.rate_limit import GraphQLResponseError

_DAY0 = datetime(2026, 11, 1, 2, 0, tzinfo=UTC)
_ALIAS_RE = re.compile(r'r(\d+): repository\(owner: "([^"]+)", name: "([^"]+)"\)')


def _iso(stamp: datetime) -> str:
    return stamp.isoformat().replace("+00:00", "Z")


class _FakeGitHub:
    """Repositories of issues, served through the batched queries the engine sends."""

    def __init__(self) -> None:
        self.issues: dict[str, dict[int, datetime]] = {}  # repo name -> number -> updatedAt
        self.night = 0
        self.full_starts: dict[str, list[int]] = {}  # repo -> nights a full fetch began
        self.resource_error_pending = False
        self.resource_errors_sent = 0
        self.renamed: dict[str, str] = {}  # old repo name -> new, as GitHub redirects

    def listing(self, _client, _org) -> list[RepositoryRecord]:
        return [RepositoryRecord(full_name=f"org/{name}", name=name, owner="org") for name in self.issues]

    def graphql(self, query: str, variables: dict) -> dict:
        if "REPO_LOOKUP_QUERY" in query:
            name = self.renamed.get(variables["repo"], variables["repo"])
            if name in self.issues:
                return {"data": {"repository": {"nameWithOwner": f"org/{name}"}}}
            raise GraphQLResponseError(
                {"data": {"repository": None}, "errors": [{"type": "NOT_FOUND", "path": ["repository"]}]}
            )
        assert "BatchedRepos" in query, "the fallback path is not expected in this simulation"
        since = variables.get("since")
        data: dict = {}
        aliases = _ALIAS_RE.findall(query)
        for index, _owner, name in aliases:
            cursor = variables[f"c{index}"]
            if since is None and cursor is None:
                self.full_starts.setdefault(name, []).append(self.night)
            data[f"r{index}"] = self._page(name, cursor, variables["pageSize"], since)
        if self.resource_error_pending and len(aliases) > 1:
            self.resource_error_pending = False
            self.resource_errors_sent += 1
            alias = f"r{aliases[0][0]}"
            data[alias] = None
            raise GraphQLResponseError(
                {
                    "data": data,
                    "errors": [
                        {
                            "type": "RESOURCE_LIMITS_EXCEEDED",
                            "path": [alias, "issues"],
                            "locations": [{"line": 2, "column": 3}],
                            "message": "Resource limits for this query exceeded.",
                        }
                    ],
                }
            )
        return {"data": data}

    def _page(self, name: str, cursor: str | None, size: int, since: str | None) -> dict:
        threshold = datetime.fromisoformat(since) if since else None
        numbers = sorted(n for n, updated in self.issues[name].items() if threshold is None or updated >= threshold)
        offset = int(cursor or 0)
        chunk = numbers[offset : offset + size]
        has_next = offset + size < len(numbers)
        nodes = [
            {
                "number": n,
                "title": f"{name} #{n}",
                "state": "OPEN",
                "createdAt": "2024-01-01T00:00:00Z",
                "closedAt": None,
                "updatedAt": _iso(self.issues[name][n]),
                "labels": {"nodes": []},
            }
            for n in chunk
        ]
        return {"issues": {"pageInfo": {"hasNextPage": has_next, "endCursor": str(offset + size)}, "nodes": nodes}}


class _Clock(datetime):
    """``datetime`` whose ``now()`` is the simulation's night."""

    current = _DAY0

    @classmethod
    def now(cls, tz=None):
        """The simulated night, whatever zone is asked for (the store always asks for UTC)."""
        del tz
        return cls.current


@pytest.fixture
def github(monkeypatch):
    """A fake GitHub org wired in as the listing, with the store's clock under the simulation's control."""
    fake = _FakeGitHub()
    monkeypatch.setattr(_common, "fetch_org_repos_graphql", fake.listing)
    monkeypatch.setattr(dataset_store, "datetime", _Clock)
    return fake


def _night(github: _FakeGitHub, night: int) -> set[tuple[str, int]]:
    dataset_store.start_run()
    github.night = night
    _Clock.current = _DAY0 + timedelta(days=night)
    records = issues.fetch_org_issues_graphql(github, "org", max_workers=1)
    return {(record.repo, record.number) for record in records}


def _dataset() -> dict:
    return json.loads((paths.DATASETS_DIR / "issues_org_all.json").read_text(encoding="utf-8"))


def test_sixty_nights_of_an_org(github):
    """Self-heal on schedule, deletion, backfill, resource error, and retirement, night by night."""
    now = _DAY0
    github.issues = {
        "active": {n: now - timedelta(days=40 - n) for n in range(1, 6)},
        "busy": {n: now - timedelta(days=20 - n) for n in range(1, 4)},
        "quiet": {1: now - timedelta(days=400)},
        **{f"lib{i}": {1: now - timedelta(days=100 + i)} for i in range(6)},
    }
    held_nights, refreshed_after_deletion, contents = [], None, {}

    for night in range(61):
        clock = _DAY0 + timedelta(days=night)
        # Daily activity: one issue of "active" changes, "busy" gains an issue every third night.
        github.issues["active"][2] = clock - timedelta(hours=3)
        if night and night % 3 == 0 and "busy" in github.issues:
            github.issues["busy"][100 + night] = clock - timedelta(hours=2)
        if night == 5:
            del github.issues["active"][1]  # deleted on GitHub
        if night == 10:
            # Transferred into the org with two years of history, all older than any watermark.
            github.issues["late"] = {n: clock - timedelta(days=700 - n) for n in range(1, 26)}
        if night == 12:
            github.resource_error_pending = True
        if night == 15:
            del github.issues["busy"]  # transferred out of the org
        if night == 20:
            github.issues["lib-zero"] = github.issues.pop("lib0")  # renamed inside the org
            github.renamed["lib0"] = "lib-zero"

        contents[night] = _night(github, night)
        dataset = _dataset()
        if any(state["holds"] for state in dataset["repos"].values()):
            held_nights.append(night)
        if night == 12:
            # (d) The resource-error night completed: nothing held, freshness advanced to tonight.
            assert github.resource_errors_sent == 1
            assert datetime.fromisoformat(dataset["fetched_at"]) == clock

    assert held_nights == []

    # (a) Every repository is fully refreshed at least once per 30 days, active ones included.
    for name, nights in github.full_starts.items():
        horizon = {"busy": 15, "lib0": 20}.get(name, 60)  # busy left on night 15; lib0 was renamed on 20
        checkpoints = [*nights, horizon]
        assert all(later - earlier <= 30 for earlier, later in zip(checkpoints, checkpoints[1:], strict=False)), name
    assert len(github.full_starts["active"]) >= 2

    # (b) The deleted issue stays through every delta and goes at active's first full refresh after night 5.
    refreshed_after_deletion = next(night for night in github.full_starts["active"] if night >= 5)
    assert all(("org/active", 1) in contents[night] for night in range(5, refreshed_after_deletion))
    assert all(("org/active", 1) not in contents[night] for night in range(refreshed_after_deletion, 61))

    # (c) The late-joining repository has its whole history the night it appears, not just what changed since.
    assert github.full_starts["late"][0] == 10
    assert {n for repo, n in contents[10] if repo == "org/late"} == set(range(1, 26))

    # A rename inside the org: the new name is backfilled and the old one retired the same night,
    # so no night ever counts the repository twice.
    assert all(not ({"org/lib0", "org/lib-zero"} <= {repo for repo, _ in contents[n]}) for n in range(61))
    assert any(repo == "org/lib-zero" for repo, _ in contents[20])

    # Retirement: busy is missing on nights 15 and 16, confirmed gone, and its rows go on night 16.
    assert any(repo == "org/busy" for repo, _ in contents[15])
    assert not any(repo == "org/busy" for repo, _ in contents[16])
    assert "org/busy" not in _dataset()["repos"]

    # Bounded nightly share: no night after the cold fetch fully refreshes more than a few repositories.
    per_night = {night: sum(night in nights for nights in github.full_starts.values()) for night in range(1, 61)}
    assert max(per_night.values()) <= 3, per_night
