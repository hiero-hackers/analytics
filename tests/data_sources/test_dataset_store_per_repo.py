"""Tests for the per-repository incremental engine (``fetch_incremental_by_repo``)."""

from __future__ import annotations

import json
import logging
import math
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from hiero_analytics.config import paths
from hiero_analytics.data_sources import dataset_store
from hiero_analytics.data_sources.dataset_store import (
    DEFAULT_OVERLAP,
    PartialOrgFetchError,
    RepoState,
    fetch_incremental_by_repo,
    load_dataset,
    save_dataset,
)

_DAY0 = datetime(2026, 11, 1, 2, 0, tzinfo=UTC)
_WINDOW = timedelta(days=30)


@dataclass(frozen=True)
class _Row:
    repo: str
    number: int
    updated_at: datetime | None


def _row(repo: str, number: int, day: float) -> _Row:
    return _Row(repo, number, _DAY0 + timedelta(days=day))


class _Org:
    """A fake org: what each repository holds, and a log of what was fetched how."""

    def __init__(self, rows: dict[str, list[_Row]]) -> None:
        self.rows = rows
        self.fail: set[str] = set()
        self.calls: list[tuple[str, tuple[str, ...], datetime | None]] = []

    def listing(self) -> list[str]:
        return list(self.rows)

    def _serve(self, names: list[str], keep) -> list[_Row]:
        out = [row for name in names if name not in self.fail for row in self.rows.get(name, []) if keep(row)]
        failing = [name for name in names if name in self.fail]
        if failing:
            raise PartialOrgFetchError(out, failing)
        return out

    def full(self, names: list[str]) -> list[_Row]:
        self.calls.append(("full", tuple(names), None))
        return self._serve(names, lambda _row: True)

    def since(self, names: list[str], since: datetime) -> list[_Row]:
        self.calls.append(("since", tuple(names), since))
        return self._serve(names, lambda row: row.updated_at is not None and row.updated_at >= since)


def _run(org: _Org, *, now: datetime, path=None, confirm_gone=None, force_full=False, window=None):
    return fetch_incremental_by_repo(
        path=path or paths.DATASETS_DIR / "rows_org_all.json",
        model_class=_Row,
        key_of=lambda row: (row.repo, row.number),
        updated_at_of=lambda row: row.updated_at,
        repo_of=lambda row: row.repo,
        list_repos=org.listing,
        full_fetch=org.full,
        since_fetch=org.since,
        confirm_gone=confirm_gone,
        force_full=force_full,
        full_refresh_after=window,
        now=now,
    )


def _stored(path=None) -> dict:
    return json.loads((path or paths.DATASETS_DIR / "rows_org_all.json").read_text(encoding="utf-8"))


def _states(path=None) -> dict[str, RepoState]:
    return {name: RepoState.from_json(raw) for name, raw in _stored(path)["repos"].items()}


def _numbers(records) -> set[tuple[str, int]]:
    return {(row.repo, row.number) for row in records}


# ---------------------------------------------------------
# planning: full, delta, backfill
# ---------------------------------------------------------


def test_first_run_fetches_every_repo_in_full_and_records_state():
    """No dataset yet: one full fetch of every listed repository; each gets a watermark and last_full_at."""
    org = _Org({"org/a": [_row("org/a", 1, -2)], "org/b": [_row("org/b", 1, -1)]})

    records = _run(org, now=_DAY0)

    assert _numbers(records) == {("org/a", 1), ("org/b", 1)}
    assert org.calls == [("full", ("org/a", "org/b"), None)]
    states = _states()
    assert set(states) == {"org/a", "org/b"}
    assert all(state.watermark == _DAY0 - timedelta(days=1) for state in states.values())
    assert all(state.last_full_at == _DAY0 for state in states.values())


def test_a_cold_fetch_staggers_the_next_full_refreshes():
    """After fetching the whole org at once, the repos must not all come due again on one night."""
    names = [f"org/r{i}" for i in range(60)]
    org = _Org({name: [_row(name, 1, -1)] for name in names})

    _run(org, now=_DAY0, window=_WINDOW)

    due_nights = Counter(
        math.floor((state.last_full_at + _WINDOW - _DAY0) / timedelta(days=1)) for state in _states().values()
    )
    assert set(due_nights) <= set(range(30))  # every repo comes due within the window (the N-day bound)
    assert max(due_nights.values()) <= 6  # spread, about 2 a night, not 60 on night 30


def test_repos_that_completed_together_share_one_delta():
    """The next run is one since-fetch for all repositories, from their shared watermark less the overlap."""
    org = _Org({"org/a": [_row("org/a", 1, -2)], "org/b": [_row("org/b", 1, -1)]})
    _run(org, now=_DAY0)
    org.rows["org/a"].append(_row("org/a", 2, 0.5))

    records = _run(org, now=_DAY0 + timedelta(days=1))

    assert _numbers(records) == {("org/a", 1), ("org/a", 2), ("org/b", 1)}
    assert org.calls[1:] == [("since", ("org/a", "org/b"), _DAY0 - timedelta(days=1) - DEFAULT_OVERLAP)]


def test_a_late_joining_repo_is_backfilled_in_full():
    """#623 (2): a repository with no state gets its whole history, not just what changed since the org watermark."""
    org = _Org({"org/a": [_row("org/a", 1, -1)]})
    _run(org, now=_DAY0)
    # Transferred in with years of history: none of it is newer than the org watermark.
    org.rows["org/late"] = [_row("org/late", n, -900 + n) for n in range(1, 21)]

    records = _run(org, now=_DAY0 + timedelta(days=1))

    assert {number for repo, number in _numbers(records) if repo == "org/late"} == set(range(1, 21))
    assert ("full", ("org/late",), None) in org.calls
    assert ("since", ("org/a",), _DAY0 - timedelta(days=1) - DEFAULT_OVERLAP) in org.calls


def test_force_full_fetches_every_repo_in_full():
    """``refresh=True`` ignores the plan: every listed repository is fetched in full."""
    org = _Org({"org/a": [_row("org/a", 1, -1)]})
    _run(org, now=_DAY0)

    _run(org, now=_DAY0 + timedelta(hours=1), force_full=True)

    assert org.calls[-1] == ("full", ("org/a",), None)


# ---------------------------------------------------------
# failures: per-repo holds and partial first fetches
# ---------------------------------------------------------


def test_a_failing_repo_holds_only_its_own_watermark():
    """One failing repository no longer holds the whole dataset back."""
    org = _Org({"org/a": [_row("org/a", 1, -2)], "org/b": [_row("org/b", 1, -1)]})
    _run(org, now=_DAY0)
    first_fetched_at = _stored()["fetched_at"]
    org.rows["org/a"].append(_row("org/a", 2, 0.5))
    org.fail = {"org/b"}

    _run(org, now=_DAY0 + timedelta(days=1))

    states = _states()
    assert states["org/a"].watermark == _DAY0 + timedelta(days=0.5)
    assert states["org/b"].watermark == _DAY0 - timedelta(days=1)  # held
    assert states["org/b"].holds == 1 and states["org/a"].holds == 0
    stored = _stored()
    assert stored["fetched_through"] == states["org/b"].watermark.isoformat()  # oldest repo, as before
    assert stored["fetched_at"] == first_fetched_at  # a partial run claims no new freshness

    # Next run: two delta groups, each from its own watermark; b recovers.
    org.fail = set()
    _run(org, now=_DAY0 + timedelta(days=2))
    assert org.calls[-2:] == [
        ("since", ("org/b",), _DAY0 - timedelta(days=1) - DEFAULT_OVERLAP),
        ("since", ("org/a",), _DAY0 + timedelta(days=0.5) - DEFAULT_OVERLAP),
    ]
    assert _states()["org/b"].holds == 0


def test_a_partial_first_fetch_is_saved_and_only_the_failed_repo_is_refetched():
    """#623 (3): the repositories that finished are kept; the failed one is fetched in full next run."""
    org = _Org({"org/a": [_row("org/a", 1, -2)], "org/b": [_row("org/b", 1, -1)]})
    org.fail = {"org/b"}

    records = _run(org, now=_DAY0)

    assert _numbers(records) == {("org/a", 1)}
    states = _states()
    assert states["org/a"].watermark is not None
    assert states["org/b"].watermark is None and states["org/b"].holds == 1
    # No prior stamp to keep, so the first fetch claims only its own watermark, not "now".
    assert _stored()["fetched_at"] == (_DAY0 - timedelta(days=2)).isoformat()

    org.fail = set()
    _run(org, now=_DAY0 + timedelta(days=1))
    assert org.calls[-2:] == [
        ("full", ("org/b",), None),
        ("since", ("org/a",), _DAY0 - timedelta(days=2) - DEFAULT_OVERLAP),
    ]
    assert _states()["org/b"].watermark is not None


def test_a_first_fetch_where_nothing_completed_raises_and_saves_nothing():
    """With no baseline and no repository finished, there is nothing worth saving."""
    org = _Org({"org/a": [_row("org/a", 1, -1)]})
    org.fail = {"org/a"}

    with pytest.raises(PartialOrgFetchError):
        _run(org, now=_DAY0)

    assert not (paths.DATASETS_DIR / "rows_org_all.json").exists()


# ---------------------------------------------------------
# the self-heal: a due full refresh replaces the repo's rows
# ---------------------------------------------------------


def test_a_due_full_refresh_replaces_the_repos_rows():
    """#623 (1): a deleted record survives every delta and disappears at the repository's next full refresh."""
    org = _Org({"org/a": [_row("org/a", 1, -2), _row("org/a", 2, -1)], "org/b": [_row("org/b", 1, -1)]})
    _run(org, now=_DAY0, window=_WINDOW)
    del org.rows["org/a"][0]  # a#1 is deleted on GitHub

    after_delta = _run(org, now=_DAY0 + timedelta(minutes=5), window=_WINDOW)
    assert ("org/a", 1) in _numbers(after_delta)  # a delta cannot see a deletion

    # The first fetch staggered the next refreshes, but none later than one window on.
    after_refresh = _run(org, now=_DAY0 + _WINDOW, window=_WINDOW)
    assert ("org/a", 1) not in _numbers(after_refresh)
    assert ("org/b", 1) in _numbers(after_refresh)
    assert _states()["org/a"].last_full_at == _DAY0 + _WINDOW


def test_a_partial_full_refresh_merges_and_stays_due():
    """A full refresh that does not finish cannot replace anything: rows are merged and the refresh retried."""
    org = _Org({"org/a": [_row("org/a", 1, -2), _row("org/a", 2, -1)]})
    _run(org, now=_DAY0, window=_WINDOW)
    seeded = _states()["org/a"].last_full_at
    del org.rows["org/a"][0]
    org.fail = {"org/a"}

    records = _run(org, now=_DAY0 + _WINDOW, window=_WINDOW)

    assert ("org/a", 1) in _numbers(records)
    assert _states()["org/a"].last_full_at == seeded  # not refreshed, so still due tomorrow
    org.fail = set()
    _run(org, now=_DAY0 + _WINDOW + timedelta(days=1), window=_WINDOW)
    assert org.calls[-1] == ("full", ("org/a",), None)


# ---------------------------------------------------------
# migration from a dataset without per-repo state
# ---------------------------------------------------------


def _legacy(rows: list[_Row], fetched_through: datetime):
    """A dataset exactly as the single-watermark code wrote it: no ``repos`` map."""
    path = paths.DATASETS_DIR / "rows_org_all.json"
    save_dataset(path, rows, fetched_through, fetched_at=fetched_through)
    assert "repos" not in _stored(path)
    return path


def test_migration_seeds_state_in_place_without_a_cold_fetch():
    """Repos with records resume from the old org watermark by delta; nothing is fetched in full tonight."""
    names = [f"org/r{i}" for i in range(4)]
    _legacy([_row(name, 1, -3) for name in names], fetched_through=_DAY0 - timedelta(days=1))
    org = _Org({name: [_row(name, 1, -3)] for name in names})

    _run(org, now=_DAY0, window=_WINDOW)

    assert [call[0] for call in org.calls] == ["since"]
    assert org.calls[0][2] == _DAY0 - timedelta(days=1) - DEFAULT_OVERLAP
    states = _states()
    assert set(states) == set(names)
    # Seeded, not stamped "now": each first full refresh lands somewhere in the next window.
    assert all(_DAY0 - _WINDOW < state.last_full_at < _DAY0 for state in states.values())


def test_migration_backfills_a_listed_repo_that_has_no_records():
    """A repository the old org-wide `since` never covered has no rows, so it gets no seed and a full fetch."""
    _legacy([_row("org/a", 1, -3)], fetched_through=_DAY0 - timedelta(days=1))
    org = _Org({"org/a": [_row("org/a", 1, -3)], "org/never-seen": [_row("org/never-seen", 5, -400)]})

    records = _run(org, now=_DAY0)

    assert ("org/never-seen", 5) in _numbers(records)
    assert ("full", ("org/never-seen",), None) in org.calls


def test_migration_spreads_first_full_refreshes_over_the_window():
    """No night of the first window carries a cold fetch: due dates are spread, and each repo comes due once."""
    names = [f"org/repo-{i}" for i in range(120)]
    current = _DAY0
    due_days = Counter()
    for name in names:
        seeded = dataset_store._seeded_last_full_at("rows_org_all.json", name, current, _WINDOW)
        due_days[math.floor((seeded + _WINDOW - current) / timedelta(days=1))] += 1

    assert sum(due_days.values()) == len(names)
    assert set(due_days) <= set(range(30))  # all within the window, none overdue on night 0
    assert max(due_days.values()) <= 3 * len(names) / 30  # 4 a night on average, never a pile-up
    # Deterministic: re-seeding the same dataset picks the same dates; another dataset picks others.
    again = dataset_store._seeded_last_full_at("rows_org_all.json", names[0], current, _WINDOW)
    other = dataset_store._seeded_last_full_at("rows_other_all.json", names[0], current, _WINDOW)
    assert again == dataset_store._seeded_last_full_at("rows_org_all.json", names[0], current, _WINDOW)
    assert other != again


def test_a_migrated_dataset_refreshes_every_repo_once_per_window_without_bunching():
    """Over the first window after migration (nights 0 to 30), each repository is fully refreshed exactly once."""
    names = [f"org/repo-{i}" for i in range(40)]
    _legacy([_row(name, 1, -3) for name in names], fetched_through=_DAY0 - timedelta(days=1))
    org = _Org({name: [_row(name, 1, -3)] for name in names})

    per_night = []
    for night in range(31):
        before = len(org.calls)
        _run(org, now=_DAY0 + timedelta(days=night), window=_WINDOW)
        per_night.append(sum(len(names) for kind, names, _ in org.calls[before:] if kind == "full"))

    refreshed = Counter(name for kind, group, _ in org.calls if kind == "full" for name in group)
    assert set(refreshed) == set(names) and set(refreshed.values()) == {1}
    assert max(per_night) <= 4  # about 1.3 a night on average


# ---------------------------------------------------------
# file layout
# ---------------------------------------------------------


def test_repo_state_is_written_after_the_records_and_old_readers_still_work():
    """``records`` stays in the identifying prefix; ``load_dataset`` (single-watermark callers) is unchanged."""
    org = _Org({"org/a": [_row("org/a", 1, -1)]})
    _run(org, now=_DAY0)
    path = paths.DATASETS_DIR / "rows_org_all.json"

    text = path.read_text(encoding="utf-8")
    assert text.index('"records"') < 256 and text.index('"records"') < text.index('"repos"')
    assert dataset_store._is_dataset_file(path)
    records, fetched_through = load_dataset(path, _Row)
    assert [row.number for row in records] == [1] and fetched_through == _DAY0 - timedelta(days=1)


def test_unreadable_repo_state_is_reseeded_not_a_cache_miss(caplog):
    """Corrupt per-repo state costs a re-seed, never the records."""
    org = _Org({"org/a": [_row("org/a", 1, -1)]})
    _run(org, now=_DAY0)
    path = paths.DATASETS_DIR / "rows_org_all.json"
    payload = _stored()
    payload["repos"] = {"org/a": "garbage"}
    path.write_text(json.dumps(payload), encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger=dataset_store.logger.name):
        records = _run(org, now=_DAY0 + timedelta(days=1))

    assert _numbers(records) == {("org/a", 1)}
    assert [call[0] for call in org.calls] == ["full", "since"]  # re-seeded: a delta, not a cold fetch
    assert any("unreadable per-repo state" in record.getMessage() for record in caplog.records)


def test_offline_returns_the_stored_records_without_listing(monkeypatch):
    """Offline runs short-circuit before the org is listed."""
    org = _Org({"org/a": [_row("org/a", 1, -1)]})
    _run(org, now=_DAY0)
    monkeypatch.setenv("HIERO_ANALYTICS_OFFLINE", "1")

    def no_listing():
        raise AssertionError("an offline run must not list the org")

    org.listing = no_listing
    records = _run(org, now=_DAY0 + timedelta(days=1))

    assert _numbers(records) == {("org/a", 1)}
    assert len(org.calls) == 1


# ---------------------------------------------------------
# retiring the rows of a repository that left the org
# ---------------------------------------------------------


def _org_of(count: int) -> _Org:
    return _Org({f"org/r{i}": [_row(f"org/r{i}", 1, -1)] for i in range(count)})


def test_a_repo_missing_once_keeps_its_rows():
    """One run without the repository in the listing changes nothing but its missing count."""
    org = _org_of(5)
    _run(org, now=_DAY0)
    del org.rows["org/r0"]
    asked = []

    records = _run(org, now=_DAY0 + timedelta(days=1), confirm_gone=lambda name: asked.append(name) or True)

    assert ("org/r0", 1) in _numbers(records)
    assert asked == []  # one absence is not evidence: no lookup yet
    assert _states()["org/r0"].missing_runs == 1


def test_a_repo_missing_twice_and_confirmed_gone_is_retired():
    """Two absent runs plus a lookup that confirms it is gone: its rows and state are dropped."""
    org = _org_of(5)
    _run(org, now=_DAY0)
    del org.rows["org/r0"]
    _run(org, now=_DAY0 + timedelta(days=1), confirm_gone=lambda _name: True)

    records = _run(org, now=_DAY0 + timedelta(days=2), confirm_gone=lambda _name: True)

    assert ("org/r0", 1) not in _numbers(records)
    assert "org/r0" not in _states()


@pytest.mark.parametrize("answer", [False, "raises"])
def test_a_missing_repo_that_cannot_be_confirmed_gone_keeps_its_rows(answer):
    """A listing gap (the repo still resolves) or a failed lookup is not evidence."""
    org = _org_of(5)
    _run(org, now=_DAY0)
    del org.rows["org/r0"]

    def confirm(_name):
        if answer == "raises":
            raise RuntimeError("lookup failed")
        return answer

    for night in (1, 2, 3):
        records = _run(org, now=_DAY0 + timedelta(days=night), confirm_gone=confirm)

    assert ("org/r0", 1) in _numbers(records)
    assert _states()["org/r0"].missing_runs == 3


def test_nothing_is_retired_when_too_many_repos_vanish_at_once():
    """Half the org missing is a broken listing, not an exodus: no lookups, no retirement."""
    org = _org_of(6)
    _run(org, now=_DAY0)
    for name in ("org/r0", "org/r1", "org/r2"):
        del org.rows[name]
    asked = []

    for night in (1, 2):
        records = _run(org, now=_DAY0 + timedelta(days=night), confirm_gone=lambda n: asked.append(n) or True)

    assert asked == []
    assert {("org/r0", 1), ("org/r1", 1), ("org/r2", 1)} <= _numbers(records)


def test_a_repo_that_comes_back_resets_its_missing_count():
    """A repository that reappears in the listing starts its missing count again."""
    org = _org_of(5)
    _run(org, now=_DAY0)
    rows = org.rows.pop("org/r0")
    _run(org, now=_DAY0 + timedelta(days=1), confirm_gone=lambda _name: True)
    org.rows["org/r0"] = rows

    _run(org, now=_DAY0 + timedelta(days=2), confirm_gone=lambda _name: True)

    assert _states()["org/r0"].missing_runs == 0


def test_a_full_refresh_that_empties_a_repo_says_so(caplog):
    """Replacing a repository's rows with nothing is allowed but never silent."""
    org = _Org({"org/a": [_row("org/a", 1, -1), _row("org/a", 2, -1)]})
    _run(org, now=_DAY0)
    org.rows["org/a"] = []

    with caplog.at_level(logging.WARNING, logger=dataset_store.logger.name):
        records = _run(org, now=_DAY0 + timedelta(hours=1), force_full=True)

    assert records == []
    assert any("full refresh of org/a returned no rows" in record.getMessage() for record in caplog.records)
