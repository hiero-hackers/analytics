"""Tests for the durable dataset store and incremental-fetch engine."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from hiero_analytics.data_sources import dataset_store
from hiero_analytics.data_sources.dataset_store import (
    OfflineDatasetMissingError,
    PartialOrgFetchError,
    fetch_incremental,
    forget_touched_datasets,
    load_dataset,
    load_or_fetch,
    merge_records,
    prune_untouched_datasets,
    save_dataset,
)


@pytest.fixture(autouse=True)
def _clear_touched():
    """The touch record is process-wide; a real run fills it exactly once."""
    forget_touched_datasets()
    yield
    forget_touched_datasets()


@dataclass(frozen=True)
class _Record:
    key: str
    value: int
    updated_at: datetime | None


def _rec(key: str, value: int, day: int) -> _Record:
    return _Record(key, value, datetime(2024, 1, day, tzinfo=UTC))


def _key(record: _Record) -> str:
    return record.key


def _updated(record: _Record) -> datetime | None:
    return record.updated_at


# ---------------------------------------------------------------------------
# merge_records
# ---------------------------------------------------------------------------


def test_merge_upserts_by_key_incoming_wins():
    """Incoming records replace existing ones by key; new keys are added."""
    existing = [_rec("a", 1, 1), _rec("b", 2, 1)]
    incoming = [_rec("b", 99, 2), _rec("c", 3, 2)]  # b updated, c new

    merged = merge_records(existing, incoming, _key)

    by_key = {r.key: r.value for r in merged}
    assert by_key == {"a": 1, "b": 99, "c": 3}


def test_merge_keeps_existing_when_no_incoming():
    """An empty incoming set leaves the existing records unchanged."""
    existing = [_rec("a", 1, 1)]
    assert merge_records(existing, [], _key) == existing


# ---------------------------------------------------------------------------
# save / load round-trip
# ---------------------------------------------------------------------------


def test_save_load_round_trip_preserves_records_and_watermark(tmp_path):
    """Records and watermark survive a save/load round-trip as typed values."""
    path = tmp_path / "issues.json"
    records = [_rec("a", 1, 1), _rec("b", 2, 3)]
    watermark = datetime(2024, 1, 3, tzinfo=UTC)

    save_dataset(path, records, watermark)
    loaded = load_dataset(path, _Record)

    assert loaded is not None
    got_records, got_through = loaded
    assert got_records == records
    assert got_through == watermark
    assert isinstance(got_records[0].updated_at, datetime)


def test_load_returns_none_when_absent(tmp_path):
    """Loading a missing dataset file returns None."""
    assert load_dataset(tmp_path / "missing.json", _Record) is None


def _rewrite_payload(path, **overrides):
    """Load the stored dataset payload, apply field overrides, and write it back."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_returns_none_on_version_mismatch(tmp_path):
    """A dataset written with an incompatible version is ignored."""
    path = tmp_path / "issues.json"
    save_dataset(path, [_rec("a", 1, 1)], datetime(2024, 1, 1, tzinfo=UTC))
    _rewrite_payload(path, version=999)
    assert load_dataset(path, _Record) is None


def test_load_returns_none_on_corrupt_watermark(tmp_path):
    """An unparseable fetched_through is treated as a cache miss, not a crash."""
    path = tmp_path / "issues.json"
    save_dataset(path, [_rec("a", 1, 1)], datetime(2024, 1, 1, tzinfo=UTC))
    _rewrite_payload(path, fetched_through="not-a-date")
    assert load_dataset(path, _Record) is None


# ---------------------------------------------------------------------------
# fetch_incremental
# ---------------------------------------------------------------------------


def test_first_run_does_full_fetch_and_stores_watermark(tmp_path):
    """With no stored dataset, a full fetch runs and the max updated_at is stored."""
    path = tmp_path / "issues.json"
    full = [_rec("a", 1, 1), _rec("b", 2, 5)]

    def full_fetch():
        return full

    def since_fetch(_since):  # must not be called on first run
        raise AssertionError("since_fetch called on first run")

    result = fetch_incremental(
        path=path,
        model_class=_Record,
        key_of=_key,
        updated_at_of=_updated,
        full_fetch=full_fetch,
        since_fetch=since_fetch,
    )

    assert {r.key for r in result} == {"a", "b"}
    _, through = load_dataset(path, _Record)
    assert through == datetime(2024, 1, 5, tzinfo=UTC)  # max updated_at


def test_second_run_fetches_since_watermark_and_merges(tmp_path):
    """With a stored dataset, only changes since the watermark are fetched and merged."""
    path = tmp_path / "issues.json"
    save_dataset(path, [_rec("a", 1, 1), _rec("b", 2, 3)], datetime(2024, 1, 3, tzinfo=UTC))

    seen_since = {}

    def full_fetch():
        raise AssertionError("full_fetch called when a dataset exists")

    def since_fetch(since):
        seen_since["since"] = since
        return [_rec("b", 99, 8), _rec("c", 3, 9)]  # b changed, c new

    result = fetch_incremental(
        path=path,
        model_class=_Record,
        key_of=_key,
        updated_at_of=_updated,
        full_fetch=full_fetch,
        since_fetch=since_fetch,
        overlap=timedelta(minutes=10),
    )

    # since = watermark - overlap
    assert seen_since["since"] == datetime(2024, 1, 3, tzinfo=UTC) - timedelta(minutes=10)
    by_key = {r.key: r.value for r in result}
    assert by_key == {"a": 1, "b": 99, "c": 3}  # a untouched, b updated, c added
    _, through = load_dataset(path, _Record)
    assert through == datetime(2024, 1, 9, tzinfo=UTC)  # new max


def test_watermark_falls_back_to_now_when_no_updated_at(tmp_path):
    """When no record carries updated_at, the watermark falls back to the injected now."""
    path = tmp_path / "issues.json"
    frozen = datetime(2030, 6, 1, tzinfo=UTC)

    fetch_incremental(
        path=path,
        model_class=_Record,
        key_of=_key,
        updated_at_of=_updated,
        full_fetch=lambda: [_Record("a", 1, None)],
        since_fetch=lambda _s: [],
        now=frozen,
    )

    _, through = load_dataset(path, _Record)
    assert through == frozen


def test_force_full_redoes_full_fetch_ignoring_dataset(tmp_path):
    """force_full does a full fetch even when a stored dataset exists."""
    path = tmp_path / "issues.json"
    save_dataset(path, [_rec("a", 1, 1)], datetime(2024, 1, 3, tzinfo=UTC))

    def since_fetch(_since):
        raise AssertionError("since_fetch called despite force_full")

    result = fetch_incremental(
        path=path,
        model_class=_Record,
        key_of=_key,
        updated_at_of=_updated,
        full_fetch=lambda: [_rec("a", 2, 5), _rec("b", 3, 5)],
        since_fetch=since_fetch,
        force_full=True,
    )

    by_key = {r.key: r.value for r in result}
    assert by_key == {"a": 2, "b": 3}  # full fetch overwrote, not merged onto old


def test_an_active_dataset_full_refreshes_once_its_last_full_fetch_is_due(tmp_path):
    """#623 (1): the newest record is recent, but the last full fetch was 60 days ago, so it is due."""
    path = tmp_path / "issues.json"
    save_dataset(
        path, [_rec("a", 1, 1)], datetime(2024, 2, 29, tzinfo=UTC), last_full_at=datetime(2024, 1, 1, tzinfo=UTC)
    )

    def since_fetch(_since):
        raise AssertionError("since_fetch called when a full refresh was due")

    result = fetch_incremental(
        path=path,
        model_class=_Record,
        key_of=_key,
        updated_at_of=_updated,
        full_fetch=lambda: [_rec("a", 9, 2)],
        since_fetch=since_fetch,
        full_refresh_after=timedelta(days=30),
        now=datetime(2024, 3, 1, tzinfo=UTC),
    )

    assert [r.value for r in result] == [9]
    assert json.loads(path.read_text(encoding="utf-8"))["last_full_at"] == "2024-03-01T00:00:00+00:00"


def test_a_quiet_dataset_no_longer_refreshes_every_night(tmp_path):
    """#623 (1): an old newest record alone used to force a full fetch every night; the last full fetch decides."""
    path = tmp_path / "issues.json"
    save_dataset(
        path, [_rec("a", 1, 1)], datetime(2024, 1, 1, tzinfo=UTC), last_full_at=datetime(2024, 2, 25, tzinfo=UTC)
    )

    def full_fetch():
        raise AssertionError("full_fetch called on a quiet dataset refreshed four days ago")

    result = fetch_incremental(
        path=path,
        model_class=_Record,
        key_of=_key,
        updated_at_of=_updated,
        full_fetch=full_fetch,
        since_fetch=lambda _s: [],
        full_refresh_after=timedelta(days=30),
        now=datetime(2024, 3, 1, tzinfo=UTC),
    )

    assert [r.key for r in result] == ["a"]
    assert json.loads(path.read_text(encoding="utf-8"))["last_full_at"] == "2024-02-25T00:00:00+00:00"  # kept


def test_a_dataset_without_last_full_at_is_seeded_rather_than_refreshed_at_once(tmp_path):
    """A file from before the stamp gets one within the next window, persisted, instead of a refresh tonight."""
    path = tmp_path / "issues.json"
    save_dataset(path, [_rec("a", 1, 1)], datetime(2024, 1, 1, tzinfo=UTC))
    now = datetime(2024, 3, 1, tzinfo=UTC)

    fetch_incremental(
        path=path,
        model_class=_Record,
        key_of=_key,
        updated_at_of=_updated,
        full_fetch=lambda: [_rec("a", 9, 2)],
        since_fetch=lambda _s: [],
        full_refresh_after=timedelta(days=30),
        now=now,
    )

    seeded = datetime.fromisoformat(json.loads(path.read_text(encoding="utf-8"))["last_full_at"])
    assert now - timedelta(days=30) < seeded <= now


def test_fresh_watermark_uses_incremental_not_full_refresh(tmp_path):
    """A watermark within full_refresh_after still uses the incremental path."""
    path = tmp_path / "issues.json"
    save_dataset(path, [_rec("a", 1, 5)], datetime(2024, 1, 5, tzinfo=UTC))

    def full_fetch():
        raise AssertionError("full_fetch called when a refresh was not due")

    result = fetch_incremental(
        path=path,
        model_class=_Record,
        key_of=_key,
        updated_at_of=_updated,
        full_fetch=full_fetch,
        since_fetch=lambda _s: [_rec("b", 2, 8)],
        full_refresh_after=timedelta(days=30),
        now=datetime(2024, 1, 10, tzinfo=UTC),  # 5 days after the watermark
    )

    assert {r.key for r in result} == {"a", "b"}


def test_offline_incremental_reuses_dataset_without_fetching(monkeypatch, tmp_path):
    """Offline mode returns the snapshot without invoking full or delta fetches."""
    path = tmp_path / "issues.json"
    records = [_rec("a", 1, 1)]
    save_dataset(path, records, datetime(2024, 1, 1, tzinfo=UTC))
    monkeypatch.setenv("HIERO_ANALYTICS_OFFLINE", "1")

    result = fetch_incremental(
        path=path,
        model_class=_Record,
        key_of=_key,
        updated_at_of=_updated,
        full_fetch=lambda: pytest.fail("full fetch called in offline mode"),
        since_fetch=lambda _since: pytest.fail("delta fetch called in offline mode"),
    )

    assert result == records


def test_offline_incremental_requires_valid_dataset(monkeypatch, tmp_path):
    """Offline mode fails clearly instead of fetching when no snapshot exists."""
    monkeypatch.setenv("HIERO_ANALYTICS_OFFLINE", "true")

    with pytest.raises(OfflineDatasetMissingError, match="Offline mode requires a valid cached dataset"):
        fetch_incremental(
            path=tmp_path / "missing.json",
            model_class=_Record,
            key_of=_key,
            updated_at_of=_updated,
            full_fetch=lambda: pytest.fail("full fetch called in offline mode"),
            since_fetch=lambda _since: pytest.fail("delta fetch called in offline mode"),
        )


# -- partial fetch: hold the watermark ----------------------------------------


def test_partial_since_fetch_merges_arrivals_but_holds_watermark(tmp_path):
    """A partial since-fetch merges what arrived but does NOT advance the watermark."""
    path = tmp_path / "issues.json"
    save_dataset(path, [_rec("a", 1, 1), _rec("b", 2, 3)], datetime(2024, 1, 3, tzinfo=UTC))

    def full_fetch():
        raise AssertionError("full_fetch must not be called on a partial since-fetch")

    def since_fetch(_since):
        # 'b' update arrived, but a repo failed after retry -> partial.
        raise PartialOrgFetchError([_rec("b", 99, 8)], failed_repos=["o/broken"])

    result = fetch_incremental(
        path=path,
        model_class=_Record,
        key_of=_key,
        updated_at_of=_updated,
        full_fetch=full_fetch,
        since_fetch=since_fetch,
    )

    by_key = {r.key: r.value for r in result}
    assert by_key == {"a": 1, "b": 99}  # arrivals merged into the baseline
    _, through = load_dataset(path, _Record)
    # Held at the prior watermark (day 3), NOT advanced to day 8, so the next
    # run re-covers the window the failed repo missed.
    assert through == datetime(2024, 1, 3, tzinfo=UTC)


def test_partial_since_fetch_holds_fetched_at_too(tmp_path):
    """A partial fetch must not claim "refreshed now" while repos are still failing.

    The failed repositories' records were last covered by the *prior* fetch, so
    the freshness stamp holds with the watermark and only advances together
    with it once a complete fetch succeeds.
    """
    path = tmp_path / "issues.json"
    save_dataset(path, [_rec("a", 1, 1)], datetime(2024, 1, 3, tzinfo=UTC))
    prior_stamp = json.loads(path.read_text())["fetched_at"]

    def since_fetch(_since):
        raise PartialOrgFetchError([_rec("b", 99, 8)], failed_repos=["o/broken"])

    fetch_incremental(
        path=path,
        model_class=_Record,
        key_of=_key,
        updated_at_of=_updated,
        full_fetch=lambda: pytest.fail("full_fetch must not be called"),
        since_fetch=since_fetch,
    )

    assert json.loads(path.read_text())["fetched_at"] == prior_stamp


def test_partial_full_fetch_first_run_reraises_and_persists_nothing(tmp_path):
    """A partial full fetch with no baseline re-raises and writes no dataset."""
    path = tmp_path / "issues.json"

    def full_fetch():
        raise PartialOrgFetchError([_rec("a", 1, 1)], failed_repos=["o/broken"])

    with pytest.raises(PartialOrgFetchError):
        fetch_incremental(
            path=path,
            model_class=_Record,
            key_of=_key,
            updated_at_of=_updated,
            full_fetch=full_fetch,
            since_fetch=lambda _s: [],
        )

    assert load_dataset(path, _Record) is None  # no incomplete baseline persisted


def test_partial_full_refresh_with_baseline_merges_and_holds_watermark(tmp_path):
    """A partial forced full refresh merges arrivals into the baseline, watermark held."""
    path = tmp_path / "issues.json"
    save_dataset(path, [_rec("a", 1, 1), _rec("b", 2, 2)], datetime(2024, 1, 2, tzinfo=UTC))

    def full_fetch():
        # forced full, but a repo failed -> only 'a' (updated) arrived.
        raise PartialOrgFetchError([_rec("a", 5, 4)], failed_repos=["o/broken"])

    result = fetch_incremental(
        path=path,
        model_class=_Record,
        key_of=_key,
        updated_at_of=_updated,
        full_fetch=full_fetch,
        since_fetch=lambda _s: [],
        force_full=True,
    )

    by_key = {r.key: r.value for r in result}
    assert by_key == {"a": 5, "b": 2}  # 'a' updated from arrivals, 'b' retained
    _, through = load_dataset(path, _Record)
    assert through == datetime(2024, 1, 2, tzinfo=UTC)  # held, not advanced to day 4


def test_load_or_fetch_reuses_persisted_dataset(monkeypatch):
    """When a fresh-enough dataset exists on disk, its records are returned without fetching."""
    persisted = ["rec-a", "rec-b"]
    recent = datetime.now(UTC) - timedelta(hours=1)
    monkeypatch.setattr(dataset_store, "load_dataset", lambda _path, _model, **_kwargs: (persisted, recent))

    fetched = []

    def fetch_fn():
        fetched.append(True)
        return ["fresh"]

    result = load_or_fetch("contributor_activity", "an-org", object, fetch_fn)

    assert result == persisted
    assert fetched == []  # the network fetch was skipped


def test_load_or_fetch_refreshes_stale_dataset(monkeypatch):
    """A dataset older than max_age triggers a refresh instead of silent reuse."""
    stale = datetime.now(UTC) - timedelta(days=30)
    monkeypatch.setattr(dataset_store, "load_dataset", lambda _path, _model, **_kwargs: (["old"], stale))

    result = load_or_fetch("contributor_activity", "an-org", object, lambda: ["fresh"])

    assert result == ["fresh"]


def test_load_or_fetch_refreshes_when_last_fetch_is_old_though_events_are_recent(tmp_path, monkeypatch):
    """The regression: a dispatch 3 days after a run must fetch, not reuse.

    The newest event (the watermark) was 3 days old, under the old 5-day gate, so
    the run served that data as the current week. Age is the last fetch's.
    """
    path = tmp_path / "widgets_org_all.json"
    monkeypatch.setattr(dataset_store, "dataset_path", lambda *_args, **_kwargs: path)
    three_days_ago = datetime.now(UTC) - timedelta(days=3)
    save_dataset(path, [_rec("a", 1, 1)], three_days_ago, fetched_at=three_days_ago)

    result = load_or_fetch("widgets", "org", _Record, lambda: ["fresh"])

    assert result == ["fresh"]


def test_load_or_fetch_reuses_a_fresh_fetch_of_a_quiet_dataset(tmp_path, monkeypatch):
    """Within a run, a dataset fetched minutes ago is reused even if its newest event is old."""
    path = tmp_path / "widgets_org_all.json"
    monkeypatch.setattr(dataset_store, "dataset_path", lambda *_args, **_kwargs: path)
    save_dataset(path, [_rec("a", 1, 1)], datetime(2024, 1, 1, tzinfo=UTC))  # fetched_at = now

    records = load_or_fetch("widgets", "org", _Record, lambda: pytest.fail("should have reused"))

    assert len(records) == 1


def test_load_or_fetch_max_age_none_disables_staleness_bound(monkeypatch):
    """max_age=None keeps the old reuse-whatever-is-on-disk behavior."""
    ancient = datetime(2024, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(dataset_store, "load_dataset", lambda _path, _model, **_kwargs: (["old"], ancient))

    result = load_or_fetch("contributor_activity", "an-org", object, lambda: ["fresh"], max_age=None)

    assert result == ["old"]


def test_load_or_fetch_falls_back_to_fetch_when_absent(monkeypatch):
    """With no persisted dataset, the fetch function is called."""
    monkeypatch.setattr(dataset_store, "load_dataset", lambda _path, _model, **_kwargs: None)

    result = load_or_fetch("issue_label_events", "an-org", object, lambda: ["fresh"])

    assert result == ["fresh"]


def test_load_or_fetch_offline_requires_dataset(monkeypatch):
    """A reuse-only caller cannot fall back to its fetch callback offline."""
    monkeypatch.setattr(dataset_store, "load_dataset", lambda _path, _model, **_kwargs: None)
    monkeypatch.setenv("HIERO_ANALYTICS_OFFLINE", "yes")

    with pytest.raises(OfflineDatasetMissingError, match="cached issue_label_events/an-org dataset"):
        load_or_fetch(
            "issue_label_events",
            "an-org",
            object,
            lambda: pytest.fail("fetch callback called in offline mode"),
        )


# -------------------------
# Pruning orphaned datasets
# -------------------------
def _stamp() -> datetime:
    return datetime(2026, 8, 6, tzinfo=UTC)


def test_prune_removes_a_dataset_no_resource_claimed(tmp_path):
    """The orphan case: a fetch was renamed, so nothing rewrites its file."""
    save_dataset(tmp_path / "live_org_all.json", [_rec("a", 1, 1)], _stamp())
    save_dataset(tmp_path / "orphan_org_all.json", [_rec("b", 2, 1)], _stamp())
    forget_touched_datasets()
    # This run claims only the live one.
    load_dataset(tmp_path / "live_org_all.json", _Record)

    removed = prune_untouched_datasets(tmp_path)

    assert [path.name for path in removed] == ["orphan_org_all.json"]
    assert (tmp_path / "live_org_all.json").exists()
    assert not (tmp_path / "orphan_org_all.json").exists()


def test_prune_keeps_a_dataset_reused_without_rewriting(tmp_path, monkeypatch):
    """Reuse must count as live — the reason mtimes cannot be the signal.

    ``load_or_fetch`` serves a dataset straight from disk for up to
    DEFAULT_REUSE_MAX_AGE, so a live dataset can be read by a run's later
    pipelines without being written.
    """
    # Redirect the store's path builder into the sandbox: the real one resolves
    # under outputs/, and a prune test must never be able to reach it.
    path = tmp_path / "widgets_org_all.json"
    monkeypatch.setattr(dataset_store, "dataset_path", lambda *_args, **_kwargs: path)
    save_dataset(path, [_rec("a", 1, 1)], datetime.now(UTC))
    forget_touched_datasets()

    records = load_or_fetch("widgets", "org", _Record, lambda: pytest.fail("should have reused"))
    removed = prune_untouched_datasets(tmp_path)

    assert len(records) == 1
    assert removed == []
    assert path.exists()


def test_prune_never_touches_files_it_does_not_own(tmp_path):
    """The datasets directory also holds the governance config and the manifest."""
    save_dataset(tmp_path / "live_org_all.json", [_rec("a", 1, 1)], _stamp())
    forget_touched_datasets()
    load_dataset(tmp_path / "live_org_all.json", _Record)
    # Neither is a save_dataset product, and neither is ever "touched".
    (tmp_path / "governance_config_org_all.json").write_text(
        json.dumps({"repositories": [{"name": ".github"}]}, indent=2), encoding="utf-8"
    )
    (tmp_path / "SNAPSHOT.json").write_text(json.dumps({"data_as_of": None}, indent=2), encoding="utf-8")

    assert prune_untouched_datasets(tmp_path) == []
    assert (tmp_path / "governance_config_org_all.json").exists()
    assert (tmp_path / "SNAPSHOT.json").exists()


def test_prune_does_nothing_when_no_dataset_was_read(tmp_path):
    """An empty touch record must never be read as "everything is an orphan"."""
    save_dataset(tmp_path / "live_org_all.json", [_rec("a", 1, 1)], _stamp())
    forget_touched_datasets()

    assert prune_untouched_datasets(tmp_path) == []
    assert (tmp_path / "live_org_all.json").exists()


def test_prune_refuses_a_directory_the_run_never_worked_in(tmp_path):
    """The safety net that matters: a run that read datasets *elsewhere*.

    Without this, a caller whose datasets live in one directory would see every
    file in an unrelated one as unclaimed and delete a live cache wholesale —
    which is exactly how this function first destroyed a local dataset dir
    during its own test run.
    """
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    save_dataset(target / "live_org_all.json", [_rec("a", 1, 1)], _stamp())
    forget_touched_datasets()
    # The run claims a dataset, but not one in `target`.
    load_dataset(elsewhere / "other_org_all.json", _Record)

    assert prune_untouched_datasets(target) == []
    assert (target / "live_org_all.json").exists()


def test_prune_reclaims_a_legacy_orphan_without_a_version_key(tmp_path):
    """The orphan that prompted this feature predates the version key.

    Its real file was pretty-printed ``{"fetched_through": ..., "records": [...]}``
    with no ``version``, so a check keyed on that alone would have shielded the
    exact file that was understating the dashboard's freshness.
    """
    save_dataset(tmp_path / "live_org_all.json", [_rec("a", 1, 1)], _stamp())
    (tmp_path / "issues_org_all.json").write_text(
        json.dumps({"fetched_through": "2026-07-11T09:25:33+00:00", "records": []}, indent=2),
        encoding="utf-8",
    )
    forget_touched_datasets()
    load_dataset(tmp_path / "live_org_all.json", _Record)

    removed = prune_untouched_datasets(tmp_path)

    assert [path.name for path in removed] == ["issues_org_all.json"]
    assert (tmp_path / "live_org_all.json").exists()


def test_prune_spares_files_the_caller_asks_to_keep(tmp_path):
    """``keep`` exempts unclaimed files the caller cannot judge (a failed org's datasets)."""
    from hiero_analytics.data_sources.dataset_store import (
        forget_touched_datasets,
        load_dataset,
        prune_untouched_datasets,
        save_dataset,
    )
    from hiero_analytics.data_sources.models import IssueTimelineEventRecord

    forget_touched_datasets()
    stamp = datetime(2026, 1, 1, tzinfo=UTC)
    for name in ("issues_live-org_all.json", "issues_failed-org_all.json", "issues_orphan-org_all.json"):
        save_dataset(tmp_path / name, [], stamp)
    forget_touched_datasets()
    load_dataset(tmp_path / "issues_live-org_all.json", IssueTimelineEventRecord)  # claimed this run

    removed = prune_untouched_datasets(tmp_path, keep=lambda path: "_failed-org_" in path.name)

    assert [path.name for path in removed] == ["issues_orphan-org_all.json"]
    assert sorted(path.name for path in tmp_path.glob("*.json")) == [
        "issues_failed-org_all.json",
        "issues_live-org_all.json",
    ]


# ---------------------------------------------------------
# per-resource record schema (#623)
# ---------------------------------------------------------


def test_a_file_written_before_schema_versions_counts_as_schema_1(tmp_path):
    """No ``schema`` key: readers at schema 1 (every resource today) load it; a bumped reader does not."""
    path = tmp_path / "issues.json"
    payload = {
        "version": dataset_store.DATASET_VERSION,
        "fetched_through": "2024-01-02T00:00:00+00:00",
        "records": [{"key": "a", "value": 1, "updated_at": "2024-01-02T00:00:00+00:00"}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert load_dataset(path, _Record) is not None
    assert load_dataset(path, _Record, schema_version=2) is None


def test_a_schema_mismatch_is_a_logged_cache_miss_for_that_dataset_only(tmp_path, caplog):
    """Bumping one resource's schema invalidates its file; a file at the expected schema still loads."""
    bumped, other = tmp_path / "issue_label_events.json", tmp_path / "issues.json"
    save_dataset(bumped, [_rec("a", 1, 1)], datetime(2024, 1, 1, tzinfo=UTC))
    save_dataset(other, [_rec("b", 2, 1)], datetime(2024, 1, 1, tzinfo=UTC))
    assert json.loads(bumped.read_text(encoding="utf-8"))["schema"] == 1

    with caplog.at_level("INFO", logger=dataset_store.logger.name):
        assert load_dataset(bumped, _Record, schema_version=2) is None
    assert load_dataset(other, _Record, schema_version=1) is not None
    assert any("record schema 1, not 2" in record.getMessage() for record in caplog.records)


def test_fetch_incremental_refetches_in_full_after_a_schema_bump(tmp_path):
    """The next run after a bump is a first fetch: full, and the file is rewritten at the new schema."""
    path = tmp_path / "hip.json"
    save_dataset(path, [_rec("a", 1, 1)], datetime(2024, 1, 1, tzinfo=UTC))

    def since_fetch(_since):
        raise AssertionError("a delta onto records of the old schema")

    result = fetch_incremental(
        path=path,
        model_class=_Record,
        key_of=_key,
        updated_at_of=_updated,
        full_fetch=lambda: [_rec("a", 7, 2)],
        since_fetch=since_fetch,
        schema_version=2,
    )

    assert [r.value for r in result] == [7]
    assert json.loads(path.read_text(encoding="utf-8"))["schema"] == 2


def test_load_or_fetch_refetches_when_the_schema_differs(monkeypatch):
    """A fresh file of another schema is not reused: the fetch runs."""
    path = dataset_store.dataset_path("label_events", "an-org")
    save_dataset(path, [_rec("a", 1, 1)], datetime.now(UTC))
    fetched = []

    def fetch_fn():
        fetched.append(True)
        return ["fresh"]

    assert load_or_fetch("label_events", "an-org", _Record, fetch_fn, schema_version=2) == ["fresh"]
    assert fetched == [True]
