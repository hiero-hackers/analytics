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
        round((state.last_full_at + _WINDOW - _DAY0) / timedelta(days=1)) for state in _states().values()
    )
    assert set(due_nights) == set(range(1, 31))  # each of the next 30 nights, never tonight: the N-day bound
    assert max(due_nights.values()) == 2  # 60 equal repos: exactly two a night, not 60 on night 30


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

    # The first fetch staggered the next refreshes, none later than one window on. Two
    # repos make a budget of one scheduled refresh a night, so the second may wait a night.
    _run(org, now=_DAY0 + _WINDOW, window=_WINDOW)
    after_refresh = _run(org, now=_DAY0 + _WINDOW + timedelta(days=1), window=_WINDOW)
    assert ("org/a", 1) not in _numbers(after_refresh)
    assert ("org/b", 1) in _numbers(after_refresh)
    assert _states()["org/a"].last_full_at in {_DAY0 + _WINDOW, _DAY0 + _WINDOW + timedelta(days=1)}


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


def test_the_stagger_balances_work_not_just_repositories():
    """Largest repos first, each on the lightest night: no night draws two of the giants.

    The production snapshot had a 40% night when a hash put two of the largest
    repositories together; three giants, ten mid-size and a hundred small ones
    must spread so the heaviest night is just the largest single repository.
    """
    weights = {f"org/giant-{i}": 1000 for i in range(3)}
    weights |= {f"org/mid-{i}": 50 for i in range(10)}
    weights |= {f"org/small-{i}": 1 for i in range(100)}

    stamps = dataset_store._stagger(weights, (), salt="rows_org_all.json", current=_DAY0, full_refresh_after=_WINDOW)

    night_of = {name: round((stamp + _WINDOW - _DAY0) / timedelta(days=1)) for name, stamp in stamps.items()}
    assert set(night_of.values()) <= set(range(1, 31))
    load, count = Counter(), Counter()
    for name, night in night_of.items():
        load[night] += weights[name]
        count[night] += 1
    assert len({night_of[f"org/giant-{i}"] for i in range(3)}) == 3
    assert max(load.values()) == 1000  # the floor: one giant, alone
    assert max(count.values()) <= math.ceil(2 * len(weights) / 30)  # within the nightly budget


def test_the_stagger_is_deterministic_and_rotated_per_dataset():
    """Same inputs, same nights; another dataset or org starts its largest repository elsewhere."""
    weights = {"org/big": 500, "org/small": 1}

    def biggest_night(salt):
        stamp = dataset_store._stagger(weights, (), salt=salt, current=_DAY0, full_refresh_after=_WINDOW)["org/big"]
        return round((stamp + _WINDOW - _DAY0) / timedelta(days=1))

    assert biggest_night("issues_org_all.json") == biggest_night("issues_org_all.json")
    nights = {
        biggest_night(f"{name}_org_all.json") for name in ("issues", "issue_label_events", "merged_pr_difficulty")
    }
    assert len(nights) == 3


def test_a_late_joiner_goes_to_the_lightest_night_of_the_existing_schedule():
    """A backfilled repository is placed around the repositories that already have nights."""
    scheduled = [(_DAY0 - _WINDOW + timedelta(days=night), 100) for night in range(1, 31) if night != 17]

    stamps = dataset_store._stagger(
        {"org/late": 40}, scheduled, salt="rows_org_all.json", current=_DAY0, full_refresh_after=_WINDOW
    )

    assert stamps["org/late"] == _DAY0 - _WINDOW + timedelta(days=17)  # the only empty night


def test_a_migrated_dataset_refreshes_every_repo_once_per_window_without_bunching():
    """Over the first window after migration, each repository is fully refreshed exactly once, never on deploy night."""
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
    assert per_night[0] == 0  # deploy night carries backfills only
    assert max(per_night) == 2  # 40 equal repos over 30 nights


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


# ---------------------------------------------------------
# step 3: the due tolerance and the nightly budget
# ---------------------------------------------------------


def test_a_run_that_starts_a_little_earlier_still_refreshes_on_time():
    """Thirty nights later, a run ten minutes earlier than the last refresh does not slip a day."""
    org = _Org({"org/a": [_row("org/a", 1, -1)]})
    _run(org, now=_DAY0, window=_WINDOW, force_full=True)

    _run(org, now=_DAY0 + _WINDOW - timedelta(minutes=10), window=_WINDOW)

    assert org.calls[-1] == ("full", ("org/a",), None)


def test_after_missed_nights_the_backlog_drains_within_the_budget_most_overdue_first():
    """Twelve nights without a run leave a backlog; it is refreshed a budget's worth a night, oldest first."""
    names = [f"org/r{i:02}" for i in range(30)]
    _legacy([_row(name, 1, -3) for name in names], fetched_through=_DAY0 - timedelta(days=1))
    org = _Org({name: [_row(name, 1, -3)] for name in names})
    _run(org, now=_DAY0, window=_WINDOW)
    due_before = {name: state.last_full_at for name, state in _states().items()}

    per_night = []
    for night in range(13, 20):  # the job comes back after nights 1 to 12 were missed
        before = len(org.calls)
        _run(org, now=_DAY0 + timedelta(days=night), window=_WINDOW)
        per_night.append([name for kind, group, _ in org.calls[before:] if kind == "full" for name in group])

    budget = math.ceil(2 * len(names) / 30)
    assert all(len(names_) <= budget for names_ in per_night)
    assert len(per_night[0]) == budget  # the backlog binds on the first night back
    drained = [name for names_ in per_night for name in names_]
    # Most overdue first: whatever a night refreshed was at least as overdue as anything a later night did.
    for earlier, later in zip(per_night, per_night[1:], strict=False):
        if earlier and later:
            assert max(due_before[name] for name in earlier) <= min(due_before[name] for name in later)
    overdue = {name for name, stamp in due_before.items() if stamp <= _DAY0 + timedelta(days=12) - _WINDOW}
    assert overdue <= set(drained)  # and it does drain


def test_backfills_are_never_deferred_by_the_budget():
    """A repository with no state is the only way to get its data, so the budget never holds it back."""
    names = [f"org/new-{i}" for i in range(10)]
    org = _Org({name: [_row(name, 1, -1)] for name in names})

    _run(org, now=_DAY0, window=_WINDOW)

    assert org.calls == [("full", tuple(names), None)]  # all ten, above a budget of one


# ---------------------------------------------------------
# step 4: per-resource schema versions
# ---------------------------------------------------------


def test_a_schema_bump_refetches_only_that_resource():
    """One resource's bump makes its dataset a first fetch; another dataset in the same run keeps its deltas."""
    bumped, untouched = paths.DATASETS_DIR / "events_org_all.json", paths.DATASETS_DIR / "rows_org_all.json"
    org_a, org_b = _Org({"org/a": [_row("org/a", 1, -1)]}), _Org({"org/a": [_row("org/a", 1, -1)]})

    def run(org, path, schema):
        return fetch_incremental_by_repo(
            path=path,
            model_class=_Row,
            key_of=lambda row: (row.repo, row.number),
            updated_at_of=lambda row: row.updated_at,
            repo_of=lambda row: row.repo,
            list_repos=org.listing,
            full_fetch=org.full,
            since_fetch=org.since,
            schema_version=schema,
            now=_DAY0,
        )

    run(org_a, bumped, 1)
    run(org_b, untouched, 1)
    run(org_a, bumped, 2)
    run(org_b, untouched, 1)

    assert [kind for kind, _, _ in org_a.calls] == ["full", "full"]
    assert [kind for kind, _, _ in org_b.calls] == ["full", "since"]
    assert _stored(bumped)["schema"] == 2 and _stored(untouched)["schema"] == 1
