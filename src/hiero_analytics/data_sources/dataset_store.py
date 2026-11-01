"""Durable dataset store for incremental fetching.

Unlike the TTL cache (``data_sources/cache.py``), this is the *system of record*:
the full accumulated dataset for a resource, persisted under ``outputs/`` together
with the high-watermark timestamp it was fetched through. Incremental fetches pull
only records changed since that watermark and merge them in, so a weekly run
re-pulls a small delta instead of all history. Org-wide datasets keep a watermark
per repository as well (:func:`fetch_incremental_by_repo`), so one failing or
late-joining repository is handled on its own instead of through the org's.

These datasets are gitignored; CI persists them between runs via the GitHub
Actions cache, while local runs keep them on disk under ``outputs/``.

This module is deliberately resource-agnostic: callers supply ``key_of`` (the
upsert identity), ``updated_at_of`` (the watermark field) and, for the per-repo
engine, ``repo_of``, so the same engine serves issues, pull requests, events, etc.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
from collections import Counter
from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, TypeVar

from hiero_analytics.config import paths
from hiero_analytics.config.paths import dataset_path

from . import dataset_health
from .dataset_health import DatasetRefresh
from .serialization import deserialize_record, serialize_record
from .usage import usage_scope

logger = logging.getLogger(__name__)

# The *file format*: the layout of a dataset file itself. Bumping it invalidates
# every dataset at once, a cold fetch of everything, so it is reserved for a
# change to the file layout. A change to one resource's records bumps that
# resource's ``schema_version`` instead (see ``DEFAULT_SCHEMA_VERSION``).
# v2: IssueTimelineEventRecord gained an ``actor`` field (from before per-resource
# schema versions existed, so it invalidated everything).
DATASET_VERSION = 2

# A resource's record schema, written as ``"schema"`` in its dataset file and
# compared on load: a mismatch makes that one dataset a cache miss, so only that
# resource is refetched in full. A file written before the key existed counts as
# schema 1. Each resource declares its own (``OrgIncrementalResource.schema_version``).
DEFAULT_SCHEMA_VERSION = 1

# Re-fetch a small window before the stored watermark so edits that landed
# mid-fetch (or under minor clock skew) are not missed. Re-merges are idempotent.
DEFAULT_OVERLAP = timedelta(minutes=10)

# How long ago a persisted dataset may have been *fetched* (its ``fetched_at``
# stamp) before load_or_fetch refreshes it instead of reusing it. It only has to
# span one run, so the pipelines of a run share the first one's fetch; every
# later run, scheduled or dispatched, pulls the delta. It once gated on the
# content watermark with the then 5-day CI cadence, so a run within 5 days of the
# newest event fetched nothing yet ended its activity windows at its own clock,
# publishing days-old data as the current week (docs/api-budget.md).
#
# Two staleness windows layer on the same dataset file, split across two levels:
# this *reuse* gate decides whether load_or_fetch calls its fetch_fn at all, and
# fetch_incremental's ~30-day *full_refresh_after* decides whether that fetch is
# a cheap since-delta or a full self-healing re-fetch.
DEFAULT_REUSE_MAX_AGE = timedelta(hours=6)


# Dataset paths this process read or wrote — what "still live" means for
# pruning. Deliberately not file mtimes: `load_or_fetch` reuses a dataset
# without rewriting it for up to DEFAULT_REUSE_MAX_AGE, and offline runs never
# rewrite one, so a perfectly live dataset can go a whole run untouched on
# disk. Reading it still registers here.
_touched_datasets: set[Path] = set()

# How much of a file to inspect when deciding whether it is one of ours.
_DATASET_PREFIX_BYTES = 256

# A repository's rows are retired only after it has been missing from the org
# listing on this many consecutive runs *and* a direct lookup confirms it is
# gone. One listing call can miss a repository, and the listing can come from a
# TTL cache that lives for days, so absence alone is never enough.
RETIRE_AFTER_MISSING_RUNS = 2
# ...and never while more than this share of a dataset's repositories is missing
# at once: that is a broken listing (a revoked token, an empty response), not an
# exodus. At least one repository may always retire, so small orgs are not stuck.
_RETIRE_MAX_MISSING_SHARE = 0.2

# A full refresh is due once ``full_refresh_after`` *less this* has passed. The
# job runs once a night but not at the same minute: without the slack, a run
# that starts ten minutes earlier than the one that did the last refresh finds
# it a few minutes short of due, and every cycle slips a day.
_DUE_TOLERANCE = timedelta(hours=12)
# At most this many times a fair share of a dataset's repositories (all of them
# over ``full_refresh_after``) get a *scheduled* full refresh in one run. The
# stagger keeps a normal night well inside it; it binds after missed nights
# (an evicted cache, a skipped save), when it drains the backlog most overdue
# first instead of refreshing everything at once.
_NIGHTLY_REFRESH_MULTIPLIER = 2


def offline_mode_enabled() -> bool:
    """Return whether analytics must avoid all network-backed fetch callbacks."""
    return os.getenv("HIERO_ANALYTICS_OFFLINE", "").strip().lower() in {"1", "true", "yes", "on"}


def touched_datasets() -> frozenset[Path]:
    """Resolved dataset paths this process has read or written."""
    return frozenset(_touched_datasets)


def forget_touched_datasets() -> None:
    """Clear the touch record (tests; a process runs the pipelines once)."""
    _touched_datasets.clear()


def _record_touch(path: Path) -> None:
    """Note that a resource claimed ``path`` this run, whether or not it existed."""
    _touched_datasets.add(path.resolve())


def _is_dataset_file(path: Path) -> bool:
    """Whether ``path`` looks like a persisted dataset, current or legacy.

    The datasets directory also holds files this module does not own — the
    pretty-printed governance config, the run's snapshot manifest — and those
    must survive pruning even though no fetch ever "touches" them.

    Requiring the schema-version key alone would be too strict in exactly the
    case that matters: the orphan that prompted this prune was written before
    ``version`` existed, so the check would have shielded it forever. Requiring
    ``records`` alongside *either* stamp keeps legacy datasets in scope while
    still excluding the manifest (which carries ``fetched_through`` inside its
    per-dataset entries, but lists ``datasets`` rather than ``records``) and the
    governance config (which has neither).
    """
    try:
        with path.open("r", encoding="utf-8") as handle:
            prefix = handle.read(_DATASET_PREFIX_BYTES)
    except OSError:
        return False
    return '"records"' in prefix and ('"version"' in prefix or '"fetched_through"' in prefix)


def prune_untouched_datasets(
    datasets_dir: Path | None = None,
    *,
    keep: Callable[[Path], bool] | None = None,
) -> list[Path]:
    """Delete persisted datasets no resource claimed this run. Returns what went.

    An orphan — a dataset whose fetch was renamed, re-scoped, or removed — is
    never rewritten but keeps riding the CI cache forever, and it dragged the
    run-level ``data_as_of`` back to whenever it was last written. Nothing else
    reclaims it: the cache restores the whole directory, and the emitter only
    ever adds.

    Only files this module wrote are considered, and only when the caller has
    established that the run was complete enough to judge — see
    :func:`touched_datasets` for why "untouched" cannot mean "old mtime". An
    empty touch record prunes nothing, so a run that fetched nothing at all can
    never mistake every dataset for an orphan.

    Note that "live" is relative to the configuration that ran: an org removed
    from the registry (``config.orgs``) or only ever run as a trial org leaves
    datasets nothing claims, and they will be removed, costing a full re-fetch
    if it is configured again later. Every deletion is logged for exactly this
    reason. A registered org the run merely did not render (``GITHUB_ORG`` or
    ``GITHUB_EXTRA_ORGS`` narrowed it) is the caller's job to exempt via
    ``keep``; ``run_all`` does.

    ``keep`` exempts files the caller cannot judge, such as the datasets of an
    org whose pipelines failed this run (they may simply not have got as far as
    their fetch).
    """
    directory = datasets_dir if datasets_dir is not None else paths.DATASETS_DIR
    if not directory.is_dir():
        return []
    # Only prune a directory this run actually worked in. Claiming nothing here
    # means the run read its datasets somewhere else entirely (a redirected
    # test sandbox, a rehearsal) and every file in *this* directory would look
    # orphaned — the one way a correct-looking prune can delete a live cache.
    resolved = directory.resolve()
    if not any(path.parent == resolved for path in _touched_datasets):
        logger.warning(
            "No dataset in %s was claimed this run; skipping prune rather than treating every file in it as an orphan",
            directory,
        )
        return []

    removed: list[Path] = []
    for path in sorted(directory.glob("*.json")):
        if path.resolve() in _touched_datasets or not _is_dataset_file(path):
            continue
        if keep is not None and keep(path):
            continue
        logger.warning(
            "Pruning orphaned dataset %s: no resource claimed it this run (it would otherwise "
            "keep understating how fresh the published data is)",
            path.name,
        )
        try:
            path.unlink()
        except OSError:
            logger.exception("Could not delete orphaned dataset %s", path)
            continue
        removed.append(path)
    if removed:
        logger.info("Pruned %d orphaned dataset(s)", len(removed))
    return removed


class OfflineDatasetMissingError(RuntimeError):
    """Offline mode was requested but no cached dataset exists for the resource.

    Subclasses RuntimeError so existing callers that treat a missing offline
    dataset as fatal keep working; callers whose output is optional (e.g. a
    single dashboard tile) can catch this specifically and skip instead.
    """


class PartialOrgFetchError(Exception):
    """Signals that an org-wide fetch could not cover every repository.

    Carries the records that *were* collected so the incremental store can merge
    them in while **holding the watermark** — the missed repos are then re-fetched
    on the next run instead of being silently skipped past (which would freeze
    them until the periodic full refresh).
    """

    def __init__(self, records: list, failed_repos: list | None = None) -> None:
        """Carry the records that arrived plus the repos still failing."""
        super().__init__(f"partial org fetch: {len(failed_repos or [])} repo(s) still failing")
        self.records = records
        self.failed_repos = failed_repos or []


# PEP 695 type parameters are intentionally avoided here because the package
# supports Python 3.11.
T = TypeVar("T")


def _parse_stamp(raw: object) -> datetime | None:
    """An ISO timestamp from a dataset file, or None when absent or malformed."""
    if not isinstance(raw, str):
        return None
    try:
        stamp = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=UTC)


@dataclass(frozen=True)
class RepoState:
    """What the store knows about one repository's slice of an org-wide dataset.

    ``watermark`` is the dataset's content watermark as of the last run in which
    this repository's fetch completed; its next delta starts there. ``None``
    means it never completed, so the next run fetches it in full.
    ``last_full_at`` is when its last complete *full* fetch finished: the
    self-heal clock, since only a full fetch can see deletions and transfers.
    ``holds`` counts consecutive runs in which its fetch failed, and
    ``missing_runs`` consecutive runs in which the org listing left it out.
    """

    watermark: datetime | None = None
    last_full_at: datetime | None = None
    holds: int = 0
    missing_runs: int = 0

    def to_json(self) -> dict[str, Any]:
        """The JSON form persisted under the dataset's ``repos`` map."""
        return {
            "watermark": self.watermark.isoformat() if self.watermark else None,
            "last_full_at": self.last_full_at.isoformat() if self.last_full_at else None,
            "holds": self.holds,
            "missing_runs": self.missing_runs,
        }

    @classmethod
    def from_json(cls, raw: object) -> RepoState:
        """Parse a persisted entry; raises ValueError on a shape this module never writes."""
        if not isinstance(raw, dict):
            raise ValueError(f"repo state must be an object, got {type(raw).__name__}")
        holds, missing_runs = raw.get("holds", 0), raw.get("missing_runs", 0)
        if not isinstance(holds, int) or not isinstance(missing_runs, int):
            raise ValueError("repo state counters must be integers")
        return cls(
            watermark=_parse_stamp(raw.get("watermark")),
            last_full_at=_parse_stamp(raw.get("last_full_at")),
            holds=holds,
            missing_runs=missing_runs,
        )


@dataclass(frozen=True)
class _StoredDataset:
    """A dataset file as loaded: records, content watermark, and per-repo state.

    ``repos`` is None for a file written before per-repo state existed (or by a
    single-file dataset that never has any); the per-repo engine seeds it.
    """

    records: list
    fetched_through: datetime
    repos: dict[str, RepoState] | None
    last_full_at: datetime | None = None
    health: dict[str, Any] = field(default_factory=dict)


def merge_records(  # noqa: UP047
    existing: Iterable[T],
    incoming: Iterable[T],
    key_of: Callable[[T], Hashable],
) -> list[T]:
    """Upsert ``incoming`` into ``existing`` keyed by ``key_of`` (incoming wins).

    Existing order is preserved for unchanged records; updated records keep their
    original position, and genuinely new records are appended.
    """
    by_key: dict[Hashable, T] = {key_of(record): record for record in existing}
    for record in incoming:
        by_key[key_of(record)] = record
    return list(by_key.values())


def _max_updated_at(  # noqa: UP047
    records: Iterable[T], updated_at_of: Callable[[T], datetime | None]
) -> datetime | None:
    """Latest non-null ``updated_at`` across records, or None if none carry one."""
    stamps = [ts for record in records if (ts := updated_at_of(record)) is not None]
    return max(stamps) if stamps else None


def save_dataset(  # noqa: UP047
    path: Path,
    records: list[T],
    fetched_through: datetime,
    *,
    fetched_at: datetime | None = None,
    last_full_at: datetime | None = None,
    repos: Mapping[str, RepoState] | None = None,
    schema_version: int = DEFAULT_SCHEMA_VERSION,
    health: Mapping[str, Any] | None = None,
) -> None:
    """Atomically write the dataset, its two stamps, and any per-repo state to ``path`` as JSON.

    The two answer different questions and must not be conflated:

    ``fetched_through`` is a *content* watermark — the latest ``updated_at``
    across the records — and drives incremental fetching ("resume from here").
    For a resource whose records carry authorship dates rather than API
    timestamps (the HIP inventory reads frontmatter ``updated:``), it tracks
    when the upstream content last changed, which may be weeks ago even on a
    fetch that just completed.

    ``fetched_at`` is wall-clock time of this write, so it answers "when did we
    last refresh this?" — the freshness question the dashboard's "data as of"
    stamp asks. Deriving that from ``fetched_through`` made a quiet fortnight in
    the HIP repository read as a fortnight-old dashboard. A caller persisting a
    *partial* fetch passes the prior stamp explicitly instead, because "now"
    would claim a freshness the failed repositories don't have.

    Added without a ``DATASET_VERSION`` bump on purpose: it is additive, its
    absence is handled explicitly by readers, and every live dataset gains it on
    the next successful run — bumping would force a full re-fetch of everything
    to acquire a field that costs nothing to backfill.

    ``last_full_at`` (when a single-file dataset was last fetched in full, see
    :func:`fetch_incremental`) and ``repos`` (see :func:`fetch_incremental_by_repo`)
    are additive for the same reason: older code ignores the key and rewrites the file without it, so a
    rollback costs nothing, and a file without it is seeded in place. It is
    written in the same atomic replace as the records, so the two can never
    disagree, and after them, so ``"records"`` stays inside the prefix that
    identifies a dataset file.
    """
    _record_touch(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "version": DATASET_VERSION,
        "schema": schema_version,
        # Ordered ahead of the records so both stamps stay inside the fixed
        # prefix `provenance` reads rather than parsing the whole file.
        "fetched_at": (fetched_at or datetime.now(UTC)).isoformat(),
        "fetched_through": fetched_through.isoformat(),
        "records": [serialize_record(record) for record in records],
    }
    if last_full_at is not None:
        payload["last_full_at"] = last_full_at.isoformat()
    if health:
        # Counters the health check needs across runs (dataset_health.py).
        payload["health"] = dict(health)
    if repos is not None:
        payload["repos"] = {name: repos[name].to_json() for name in sorted(repos)}
    with NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as tmp:
        # Compact separators: these files are machine-read only, and pretty-printing
        # a large dataset is meaningfully slower and bigger on disk.
        json.dump(payload, tmp, separators=(",", ":"))
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


_FETCHED_AT_PREFIX_RE = re.compile(r'"fetched_at"\s*:\s*"([^"]+)"')
_STAMP_PREFIX_BYTES = 256  # both stamps are written at the head of the file


def _read_prior_fetched_at(path: Path) -> datetime | None:
    """The existing file's ``fetched_at`` stamp, or None (absent file or legacy format).

    Read from the fixed prefix ``save_dataset`` writes the stamps into, the
    same way ``provenance`` reads it — cheap enough to call on the partial-fetch
    path without re-parsing a large dataset.
    """
    try:
        with path.open("r", encoding="utf-8") as handle:
            prefix = handle.read(_STAMP_PREFIX_BYTES)
    except OSError:
        return None
    match = _FETCHED_AT_PREFIX_RE.search(prefix)
    if match is None:
        return None
    try:
        stamp = datetime.fromisoformat(match.group(1))
    except ValueError:
        return None
    return stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=UTC)


def _load_stored(path: Path, model_class: type, schema_version: int = DEFAULT_SCHEMA_VERSION) -> _StoredDataset | None:
    """Load a dataset file with its per-repo state, or None if absent or incompatible.

    Incompatible means another file format (``DATASET_VERSION``) or another
    record schema than the caller's ``schema_version``.
    """
    # Before the existence check on purpose: a resource asking for this path is
    # what marks it live, whether or not a file is there yet. Every read route
    # (load_or_fetch's reuse, the incremental fetchers' baseline) passes through here.
    _record_touch(path)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):  # fmt: skip
        return None
    if payload.get("version") != DATASET_VERSION:
        return None
    stored_schema = payload.get("schema", DEFAULT_SCHEMA_VERSION)
    if stored_schema != schema_version:
        # Worth a line: it is about to cost a full fetch of this resource.
        logger.info(
            "Dataset %s has record schema %s, not %s; refetching this resource in full",
            path.name,
            stored_schema,
            schema_version,
        )
        return None
    raw_through = payload.get("fetched_through")
    if not isinstance(raw_through, str):
        return None
    # A corrupted/partially-written dataset (bad record shapes, unparseable
    # timestamp) is treated as a cache miss rather than crashing the fetch — the
    # caller then does a full fetch and rewrites a clean dataset.
    try:
        records = [deserialize_record(model_class, record) for record in payload.get("records", [])]
        fetched_through = datetime.fromisoformat(raw_through)
    except (TypeError, ValueError, KeyError, AttributeError):  # fmt: skip
        return None
    repos: dict[str, RepoState] | None = None
    raw_repos = payload.get("repos")
    if raw_repos is not None:
        # Unreadable per-repo state is re-seeded from the watermark rather than
        # costing the records: the records are the expensive part.
        try:
            if not isinstance(raw_repos, dict):
                raise ValueError("repos must be an object")
            repos = {str(name): RepoState.from_json(state) for name, state in raw_repos.items()}
        except ValueError:
            logger.warning("Dataset %s has unreadable per-repo state; re-seeding it", path.name)
            repos = None
    health = payload.get("health")
    return _StoredDataset(
        records,
        fetched_through,
        repos,
        _parse_stamp(payload.get("last_full_at")),
        health if isinstance(health, dict) else {},
    )


def load_dataset(  # noqa: UP047
    path: Path, model_class: type[T], *, schema_version: int = DEFAULT_SCHEMA_VERSION
) -> tuple[list[T], datetime] | None:
    """Load ``(records, fetched_through)``, or None if absent or incompatible."""
    stored = _load_stored(path, model_class, schema_version)
    return None if stored is None else (stored.records, stored.fetched_through)


def load_or_fetch(  # noqa: UP047
    resource: str,
    org: str,
    model_class: type[T],
    fetch_fn: Callable[[], list[T]],
    *,
    max_age: timedelta | None = DEFAULT_REUSE_MAX_AGE,
    fingerprint: str = "all",
    schema_version: int = DEFAULT_SCHEMA_VERSION,
) -> list[T]:
    """Reuse the persisted ``(resource, org)`` dataset if fresh enough, else build it.

    Wraps :func:`load_dataset` with a fetch fallback and consistent logging, so the
    runners don't each re-implement the reuse-or-fetch dance. ``fetch_fn`` produces
    the full record list when there is no usable dataset on disk, and is also called
    when the dataset was last fetched more than ``max_age`` ago — a standalone run
    therefore never silently serves arbitrarily old data. ``fetch_fn`` is normally an
    incremental fetcher, so a stale-triggered refresh only pulls the delta (and
    re-persists the dataset). ``max_age=None`` disables the staleness bound.

    Age is measured from ``fetched_at``, not the ``fetched_through`` content
    watermark: the watermark is the newest event, which says nothing about when
    the events after it were last looked for. A legacy file without
    ``fetched_at`` falls back to the watermark.

    ``fingerprint`` must match what ``fetch_fn`` writes (the incremental
    fetchers derive it from their query variables, e.g. issue states) — a
    mismatch would read one dataset while writing another. ``schema_version``
    must match too, or every call misses and refetches.
    """
    path = dataset_path(resource, org, fingerprint)
    state = load_dataset(path, model_class, schema_version=schema_version)
    if state is not None:
        records, fetched_through = state
        if offline_mode_enabled():
            logger.info("Reusing offline %s/%s dataset (%d records)", org, resource, len(records))
            return records
        last_fetched = _read_prior_fetched_at(path) or fetched_through
        if last_fetched.tzinfo is None:
            last_fetched = last_fetched.replace(tzinfo=UTC)
        if max_age is None or last_fetched >= datetime.now(UTC) - max_age:
            logger.info("Reusing persisted %s/%s dataset (%d records)", org, resource, len(records))
            return records
        logger.info(
            "Persisted %s/%s dataset is stale (fetched at %s, through %s); refreshing",
            org,
            resource,
            last_fetched.isoformat(),
            fetched_through.isoformat(),
        )
        with usage_scope(org=org, dataset=resource):
            return fetch_fn()
    if offline_mode_enabled():
        raise OfflineDatasetMissingError(f"Offline mode requires a cached {resource}/{org} dataset")
    logger.info("No persisted %s/%s dataset; fetching from GitHub", org, resource)
    with usage_scope(org=org, dataset=resource):
        return fetch_fn()


def fetch_incremental(  # noqa: UP047
    *,
    path: Path,
    model_class: type[T],
    key_of: Callable[[T], Hashable],
    updated_at_of: Callable[[T], datetime | None],
    full_fetch: Callable[[], list[T]],
    since_fetch: Callable[[datetime], list[T]],
    overlap: timedelta = DEFAULT_OVERLAP,
    force_full: bool = False,
    full_refresh_after: timedelta | None = None,
    schema_version: int = DEFAULT_SCHEMA_VERSION,
    now: datetime | None = None,
) -> list[T]:
    """Fetch a resource incrementally, persisting the merged dataset.

    The first run (no stored dataset) does a full fetch. Subsequent runs fetch
    only records updated since ``watermark - overlap`` and merge them in. The new
    watermark is the latest ``updated_at`` across the merged set, falling back to
    the current time when no record carries one.

    Self-heal controls: ``force_full`` re-does a full fetch ignoring any stored
    dataset; ``full_refresh_after`` forces a full fetch once the last *complete
    full fetch* (the stored ``last_full_at``) is that old, reclaiming
    deleted/missed records that an incremental ``since`` query can never see.
    It used to compare the content watermark instead, which never fired on an
    active dataset (its newest record is always recent) and fired every night on
    a quiet one. A file that predates the stamp gets a seeded one, spread over
    the next window, rather than an immediate refresh.

    Partial fetches: if ``full_fetch``/``since_fetch`` raise
    :class:`PartialOrgFetchError` (some repos failed even after retry), the records
    that *did* arrive are merged in, but the **watermark is held** at its prior
    value so the next run re-covers the gap. The one exception is a partial fetch
    on the very first run (no prior baseline): we refuse to persist an incomplete
    snapshot with an advanced watermark and re-raise instead.
    """
    current = now or datetime.now(UTC)
    stored = _load_stored(path, model_class, schema_version)
    state = None if stored is None else (stored.records, stored.fetched_through)
    if offline_mode_enabled():
        if state is None:
            raise OfflineDatasetMissingError(f"Offline mode requires a valid cached dataset at {path}")
        records, _ = state
        logger.info("Reusing offline dataset %s (%d records)", path, len(records))
        return records
    last_full_at = stored.last_full_at if stored is not None else None
    if stored is not None and last_full_at is None and full_refresh_after is not None:
        last_full_at = _seeded_last_full_at(path.name, "", current, full_refresh_after)
    is_stale = (
        full_refresh_after is not None
        and last_full_at is not None
        and last_full_at <= current - full_refresh_after + _DUE_TOLERANCE
    )
    held_watermark: datetime | None = None
    if state is None or force_full or is_stale:
        try:
            records = full_fetch()
            last_full_at = current
        except PartialOrgFetchError as exc:
            if state is None:
                raise  # no baseline to fall back on; don't persist a partial one
            records = merge_records(state[0], exc.records, key_of)
            held_watermark = state[1]
    else:
        existing, fetched_through = state
        try:
            incoming = since_fetch(fetched_through - overlap)
        except PartialOrgFetchError as exc:
            incoming = exc.records
            held_watermark = fetched_through
        records = merge_records(existing, incoming, key_of)

    watermark = held_watermark or _max_updated_at(records, updated_at_of) or current
    # A partial fetch holds the freshness stamp as well as the watermark: some
    # repositories were not covered, so "refreshed now" would overstate what
    # the dashboard's data-as-of bound can promise. The prior stamp (or, for a
    # legacy file without one, the held watermark) is the honest claim; both
    # stamps advance together once a complete fetch succeeds.
    preserved_fetched_at = None
    if held_watermark is not None:
        preserved_fetched_at = _read_prior_fetched_at(path) or held_watermark
    prior_health = stored.health if stored is not None else {}
    holds = int(prior_health.get("holds", 0)) + 1 if held_watermark is not None else 0
    rows_before = len(state[0]) if state is not None else 0
    shrink_streak = int(prior_health.get("runs_without_shrink", 0)) + 1 if len(records) >= rows_before else 0
    overdue = {}
    if (
        full_refresh_after is not None
        and last_full_at is not None
        and last_full_at < current - full_refresh_after - dataset_health.OVERDUE_GRACE
    ):
        overdue[dataset_health.WHOLE_DATASET] = last_full_at.isoformat()
    full = state is None or force_full or is_stale
    dataset_health.record(
        DatasetRefresh(
            dataset=path.stem,
            rows_before=rows_before,
            rows_after=len(records),
            full_refreshed=[dataset_health.WHOLE_DATASET] if full and held_watermark is None else [],
            held={dataset_health.WHOLE_DATASET: holds} if holds else {},
            # A delta merge only adds or updates: fewer rows after one is a bug.
            unexplained_loss=(
                {dataset_health.WHOLE_DATASET: rows_before - len(records)}
                if not full and len(records) < rows_before
                else {}
            ),
            overdue=overdue,
            runs_without_shrink=shrink_streak,
        )
    )
    save_dataset(
        path,
        records,
        watermark,
        fetched_at=preserved_fetched_at,
        last_full_at=last_full_at,
        schema_version=schema_version,
        health={"holds": holds, "runs_without_shrink": shrink_streak},
    )
    return records


# ---------------------------------------------------------------------------
# Per-repository incremental fetching for org-wide datasets
# ---------------------------------------------------------------------------


def _seeded_last_full_at(salt: str, item: str, current: datetime, full_refresh_after: timedelta) -> datetime:
    """A ``last_full_at`` that brings ``item`` due at a stable, hash-chosen point of the next window.

    For a single-file dataset that predates the stamp: there is one item, so
    there is nothing to balance, only the need not to come due on the night of
    the upgrade. ``hashlib``, not ``hash()``: the builtin is salted per process.
    """
    digest = hashlib.sha256(f"{salt}\0{item}".encode()).digest()
    fraction = int.from_bytes(digest[:8], "big") / 2**64
    return current - full_refresh_after * (1 - fraction)


def _nights(full_refresh_after: timedelta) -> int:
    """How many nightly runs one refresh window spans."""
    return max(1, round(full_refresh_after / timedelta(days=1)))


def _pages(rows: int) -> int:
    """Rough cost of a repository's full fetch, in pages: what the stagger balances."""
    return max(1, math.ceil(rows / 100))


def _nights_until_due(last_full_at: datetime, current: datetime, full_refresh_after: timedelta) -> int:
    """Runs from now until a full refresh stamped ``last_full_at`` comes due (0: due now)."""
    due_at = last_full_at + full_refresh_after - _DUE_TOLERANCE
    return max(0, math.ceil((due_at - current) / timedelta(days=1)))


def _stagger(
    weights: Mapping[str, int],
    scheduled: Iterable[tuple[datetime, int]],
    *,
    salt: str,
    current: datetime,
    full_refresh_after: timedelta,
    phase: float | None = None,
) -> dict[str, datetime]:
    """Choose ``last_full_at`` stamps that spread the next full refreshes of ``weights``' repositories.

    Each repository comes due on one of the next ``full_refresh_after`` nights
    (1 to N, never tonight), so the N-day bound holds from the start. They are
    placed largest first, each on the night with the least work already on it:
    ``scheduled`` (the due stamps and weights of repositories that keep theirs)
    plus the ones placed so far. A hash spreads *repositories* evenly but not
    work: on the production snapshot it put two of the largest on one night, 40%
    of a dataset. Ties go to the night with fewer repositories, then to a
    starting night: ``phase`` (a fraction of the window) when the caller
    coordinates several datasets, so an org's largest repositories never share
    a night across datasets; otherwise one rotated by ``salt``. Deterministic
    for the same inputs.
    """
    nights = _nights(full_refresh_after)
    load = dict.fromkeys(range(1, nights + 1), 0)
    count = dict.fromkeys(range(1, nights + 1), 0)
    for last_full_at, weight in scheduled:
        night = _nights_until_due(last_full_at, current, full_refresh_after)
        if night in load:
            load[night] += weight
            count[night] += 1
    if phase is None:
        rotation = int.from_bytes(hashlib.sha256(salt.encode()).digest()[:8], "big") % nights
    else:
        rotation = round(phase * nights) % nights

    def tie_break(name: str) -> bytes:
        return hashlib.sha256(f"{salt}\0{name}".encode()).digest()

    stamps: dict[str, datetime] = {}
    for name in sorted(weights, key=lambda n: (-weights[n], tie_break(n))):
        night = min(load, key=lambda n: (load[n], count[n], (n - 1 - rotation) % nights))
        load[night] += weights[name]
        count[night] += 1
        # Due on exactly that night: the tolerance absorbs the run's start time.
        stamps[name] = current - full_refresh_after + timedelta(days=night)
    return stamps


def _seed_repo_states(
    records: list,
    fetched_through: datetime,
    repo_of: Callable[[Any], str],
    *,
    salt: str,
    current: datetime,
    full_refresh_after: timedelta | None,
    phase: float | None = None,
) -> dict[str, RepoState]:
    """Per-repo state for a dataset written before it existed, without fetching anything.

    Every repository that has records resumes from the file's org-wide
    watermark, exactly where the old code would have resumed it, with a
    staggered ``last_full_at`` (:func:`_stagger`) so its first full refresh lands
    on one of the next N nights rather than tonight. A listed repository with *no*
    records gets no state, so it is fetched in full on the next run: cheap if it
    really is empty, and the backfill a late-joining repository needs.
    """
    rows = Counter(name for record in records if (name := repo_of(record)))
    stamps = (
        _stagger(
            {name: _pages(n) for name, n in rows.items()},
            (),
            salt=salt,
            current=current,
            full_refresh_after=full_refresh_after,
            phase=phase,
        )
        if full_refresh_after
        else {}
    )
    return {name: RepoState(watermark=fetched_through, last_full_at=stamps.get(name)) for name in sorted(rows)}


def _due(state: RepoState, current: datetime, full_refresh_after: timedelta | None) -> bool:
    """Whether the repository's periodic full refresh is due (within ``_DUE_TOLERANCE``)."""
    if full_refresh_after is None:
        return False
    return state.last_full_at is None or state.last_full_at <= current - full_refresh_after + _DUE_TOLERANCE


def _failed_name(repo: object) -> str:
    """The ``owner/name`` a failed-repo entry stands for (a RepositoryRecord or a plain name)."""
    full_name = getattr(repo, "full_name", None)
    return full_name if isinstance(full_name, str) else str(repo)


def _collect(fetch: Callable[[list[str]], list[T]], names: list[str], failed: set[str]) -> list[T]:  # noqa: UP047
    """Run one fetch group, noting the repositories a partial fetch reports as failed."""
    try:
        return fetch(names)
    except PartialOrgFetchError as exc:
        failed.update(_failed_name(repo) for repo in exc.failed_repos)
        return list(exc.records)


def _retire_missing(
    path: Path,
    missing: dict[str, RepoState],
    total: int,
    confirm_gone: Callable[[str], bool] | None,
) -> set[str]:
    """The missing repositories whose rows should go, under the rules on ``RETIRE_AFTER_MISSING_RUNS``."""
    candidates = sorted(name for name, state in missing.items() if state.missing_runs >= RETIRE_AFTER_MISSING_RUNS)
    if not candidates or confirm_gone is None:
        return set()
    if len(missing) > max(1, int(_RETIRE_MAX_MISSING_SHARE * total)):
        logger.warning(
            "%s: %d of %d repositories are missing from the org listing at once; retiring none, "
            "since that looks like a broken listing rather than repositories leaving",
            path.name,
            len(missing),
            total,
        )
        return set()
    retired: set[str] = set()
    for name in candidates:
        try:
            gone = confirm_gone(name)
        except Exception:
            logger.warning("Could not confirm whether %s is gone; keeping its rows in %s", name, path.name)
            continue
        if gone:
            logger.warning(
                "Retiring %s from %s: missing from the org listing for %d runs and no longer resolvable under that name",
                name,
                path.name,
                missing[name].missing_runs,
            )
            retired.add(name)
        else:
            logger.info("%s is missing from the org listing but still exists; keeping its rows in %s", name, path.name)
    return retired


def fetch_incremental_by_repo(  # noqa: UP047
    *,
    path: Path,
    model_class: type[T],
    key_of: Callable[[T], Hashable],
    updated_at_of: Callable[[T], datetime | None],
    repo_of: Callable[[T], str],
    list_repos: Callable[[], Sequence[str]],
    full_fetch: Callable[[list[str]], list[T]],
    since_fetch: Callable[[list[str], datetime], list[T]],
    confirm_gone: Callable[[str], bool] | None = None,
    overlap: timedelta = DEFAULT_OVERLAP,
    force_full: bool = False,
    full_refresh_after: timedelta | None = None,
    stagger_phase: float | None = None,
    schema_version: int = DEFAULT_SCHEMA_VERSION,
    now: datetime | None = None,
) -> list[T]:
    """Fetch an org-wide dataset incrementally, keeping a watermark per repository.

    :func:`fetch_incremental` keeps one watermark for the whole org, so a
    repository that joined after it was only ever fetched from that point on,
    and one failing repository held everyone back. Here each repository listed
    by ``list_repos`` (``owner/name``) is planned on its own:

    - no state yet (new, late-joining, or a first fetch that failed): a full
      fetch of that repository, which is the backfill;
    - its periodic full refresh is due (``last_full_at`` older than
      ``full_refresh_after``), or ``force_full``: a full fetch;
    - otherwise: a delta from its own watermark. Repositories that completed
      together share a watermark, so a delta is usually one ``since_fetch``.

    A repository whose full fetch completes has its rows *replaced*: that is
    where deleted and transferred records go. Everything else is merged. A
    repository the fetch reports as failed (:class:`PartialOrgFetchError`) keeps
    its rows and its watermark, and is planned the same way next run; the others
    advance. A first fetch in which some repositories completed is saved, with
    the failed ones left without state, rather than discarded; only a first
    fetch in which *nothing* completed re-raises.

    A dataset written before per-repo state existed is seeded in place (see
    :func:`_seed_repo_states`), so the switch costs no cold fetch. A repository
    that drops out of the listing keeps its rows until the retirement rules
    hold (``RETIRE_AFTER_MISSING_RUNS``, confirmed by ``confirm_gone``).

    ``full_fetch`` and ``since_fetch`` receive repository names; the caller maps
    them back to whatever its fetchers need. ``stagger_phase`` (see
    :func:`_stagger`) lets the caller keep several datasets' largest
    repositories on different nights. A stored dataset of another
    ``schema_version`` is treated as absent: a first fetch of this resource
    only, with the partial-first-fetch and stagger rules above.
    """
    current = now or datetime.now(UTC)
    stored = _load_stored(path, model_class, schema_version)
    if offline_mode_enabled():
        if stored is None:
            raise OfflineDatasetMissingError(f"Offline mode requires a valid cached dataset at {path}")
        logger.info("Reusing offline dataset %s (%d records)", path, len(stored.records))
        return stored.records

    existing: list[T] = stored.records if stored is not None else []
    if stored is None:
        states: dict[str, RepoState] = {}
    elif stored.repos is None:
        states = _seed_repo_states(
            existing,
            stored.fetched_through,
            repo_of,
            salt=path.name,
            current=current,
            full_refresh_after=full_refresh_after,
            phase=stagger_phase,
        )
        logger.info(
            "Dataset %s has no per-repo state yet; seeded %d repositories from its watermark %s",
            path.name,
            len(states),
            stored.fetched_through.isoformat(),
        )
    else:
        states = dict(stored.repos)

    listed = list(dict.fromkeys(list_repos()))
    backfill = [name for name in listed if (state := states.get(name)) is None or state.watermark is None]
    without_state = set(backfill)
    due = [
        name
        for name in listed
        if name not in without_state and (force_full or _due(states[name], current, full_refresh_after))
    ]
    deferred: list[str] = []
    if full_refresh_after is not None and not force_full:
        budget = math.ceil(_NIGHTLY_REFRESH_MULTIPLIER * len(listed) / _nights(full_refresh_after))
        if len(due) > budget:
            # Most overdue first; backfills are never deferred (they are the only
            # way to get that data at all) and do not count against the budget.
            due.sort(key=lambda name: (states[name].last_full_at or datetime.min.replace(tzinfo=UTC), name))
            due, deferred = due[:budget], due[budget:]
            logger.info(
                "%s: %d full refreshes are due; doing the %d most overdue tonight and deferring %d",
                path.name,
                len(due) + len(deferred),
                budget,
                len(deferred),
            )
    fetch_in_full = without_state | set(due)
    full_names = [name for name in listed if name in fetch_in_full]
    delta_groups: dict[datetime, list[str]] = {}
    for name in listed:
        watermark = states[name].watermark if name in states else None
        if name not in fetch_in_full and watermark is not None:
            delta_groups.setdefault(watermark, []).append(name)
    logger.info(
        "%s: %d repositories to fetch in full (%d without state, %d due), %d by delta",
        path.name,
        len(full_names),
        len(backfill),
        len(due),
        sum(len(group) for group in delta_groups.values()),
    )

    failed: set[str] = set()
    full_records = _collect(full_fetch, full_names, failed) if full_names else []
    delta_records: list[T] = []
    for watermark in sorted(delta_groups):
        since = watermark - overlap
        delta_records.extend(
            _collect(lambda names, since=since: since_fetch(names, since), delta_groups[watermark], failed)
        )

    if stored is None and listed and failed.issuperset(listed):
        # Nothing completed and there is no baseline: saving would persist an
        # empty or fragmentary dataset as if it were a start.
        raise PartialOrgFetchError([*full_records, *delta_records], sorted(failed))

    refreshed = {name for name in full_names if name not in failed}
    if refreshed:
        had = Counter(repo_of(record) for record in existing)
        arrived = Counter(repo_of(record) for record in full_records)
        for name in sorted(refreshed):
            if had[name] and not arrived[name]:
                # Legitimate (every record deleted, issues disabled) but never routine:
                # say so, since nothing else will.
                logger.warning(
                    "%s: full refresh of %s returned no rows; replacing its %d rows with none",
                    path.name,
                    name,
                    had[name],
                )
            elif had[name]:
                logger.info(
                    "%s: full refresh of %s replaced %d rows with %d", path.name, name, had[name], arrived[name]
                )
    kept = [record for record in existing if repo_of(record) not in refreshed]
    records = merge_records(kept, [*full_records, *delta_records], key_of)

    listed_names = set(listed)
    missing = {
        name: replace(state, missing_runs=state.missing_runs + 1)
        for name, state in states.items()
        if name not in listed_names
    }
    retired = _retire_missing(path, missing, len(states), confirm_gone)
    if retired:
        records = [record for record in records if repo_of(record) not in retired]

    content = _max_updated_at(records, updated_at_of) or current
    new_states: dict[str, RepoState] = {}
    first_full: list[str] = []
    for name in listed:
        prior = states.get(name, RepoState())
        if name in failed:
            new_states[name] = replace(prior, holds=prior.holds + 1, missing_runs=0)
            continue
        if name in refreshed and prior.watermark is None and full_refresh_after is not None:
            # Its first full fetch: stamped below with the others, so that after a
            # cold fetch of the whole org they do not all come due on one night.
            first_full.append(name)
        last_full_at = current if name in refreshed else prior.last_full_at
        new_states[name] = RepoState(watermark=content, last_full_at=last_full_at)
    new_states.update((name, state) for name, state in missing.items() if name not in retired)
    if first_full and full_refresh_after is not None:
        rows = Counter(repo_of(record) for record in records)
        stamps = _stagger(
            {name: _pages(rows[name]) for name in first_full},
            (
                (state.last_full_at, _pages(rows[name]))
                for name, state in new_states.items()
                if name not in first_full and state.last_full_at is not None
            ),
            salt=path.name,
            current=current,
            full_refresh_after=full_refresh_after,
            phase=stagger_phase,
        )
        for name, stamp in stamps.items():
            new_states[name] = replace(new_states[name], last_full_at=stamp)

    if failed:
        logger.warning(
            "%s: holding the watermark of %d repositories this run: %s",
            path.name,
            len(failed),
            ", ".join(sorted(failed)),
        )
    # The dataset-level watermark is the point through which *every* listed
    # repository is known complete, which is what the single-watermark format
    # always meant: the oldest per-repo watermark, or the content watermark.
    fetched_through = min(
        (state.watermark for name, state in new_states.items() if name in listed_names and state.watermark),
        default=content,
    )
    # A run that missed repositories keeps the prior freshness stamp, as a held
    # watermark always did; a first fetch has none, so it claims no more than
    # its own watermark.
    preserved_fetched_at = (_read_prior_fetched_at(path) or fetched_through) if failed else None

    # What this refresh did, for SNAPSHOT.json and the health check.
    prior_health = stored.health if stored is not None else {}
    shrink_streak = int(prior_health.get("runs_without_shrink", 0)) + 1 if len(records) >= len(existing) else 0
    rows_had, rows_have = (
        Counter(repo_of(record) for record in existing),
        Counter(repo_of(record) for record in records),
    )
    overdue = {}
    if full_refresh_after is not None:
        cutoff = current - full_refresh_after - dataset_health.OVERDUE_GRACE
        overdue = {
            name: state.last_full_at.isoformat()
            for name, state in new_states.items()
            if name in listed_names and state.last_full_at is not None and state.last_full_at < cutoff
        }
    dataset_health.record(
        DatasetRefresh(
            dataset=path.stem,
            rows_before=len(existing),
            rows_after=len(records),
            full_refreshed=sorted(refreshed),
            backfilled=sorted(name for name in backfill if name in refreshed),
            deferred=sorted(deferred),
            held={name: new_states[name].holds for name in sorted(failed) if name in new_states},
            retired=sorted(retired),
            # A delta merge only adds or updates rows, so a repository that was
            # neither refreshed nor retired can never lose any: if it did, the
            # upsert identity is wrong (two repositories sharing keys, say).
            unexplained_loss={
                name: rows_had[name] - rows_have[name]
                for name in sorted(rows_had)
                if rows_have[name] < rows_had[name] and name not in refreshed and name not in retired
            },
            overdue=overdue,
            runs_without_shrink=shrink_streak,
        )
    )
    save_dataset(
        path,
        records,
        fetched_through,
        fetched_at=preserved_fetched_at,
        repos=new_states,
        schema_version=schema_version,
        health={"runs_without_shrink": shrink_streak},
    )
    return records
