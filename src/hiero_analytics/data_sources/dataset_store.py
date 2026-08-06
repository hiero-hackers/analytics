"""Durable dataset store for incremental fetching.

Unlike the TTL cache (``data_sources/cache.py``), this is the *system of record*:
the full accumulated dataset for a resource, persisted under ``outputs/`` together
with the high-watermark timestamp it was fetched through. Incremental fetches pull
only records changed since that watermark and merge them in, so a weekly run
re-pulls a small delta instead of all history.

These datasets are gitignored; CI persists them between runs via the GitHub
Actions cache, while local runs keep them on disk under ``outputs/``.

This module is deliberately resource-agnostic: callers supply ``key_of`` (the
upsert identity) and ``updated_at_of`` (the watermark field) so the same engine
serves issues, pull requests, events, etc.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable, Hashable, Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TypeVar

from hiero_analytics.config import paths
from hiero_analytics.config.paths import dataset_path

from .serialization import deserialize_record, serialize_record

logger = logging.getLogger(__name__)

# Bump to invalidate persisted datasets after a schema change so the next run does
# one full refresh. v2: IssueTimelineEventRecord gained an ``actor`` field, so older
# label-event datasets must be re-fetched to populate it.
DATASET_VERSION = 2

# Re-fetch a small window before the stored watermark so edits that landed
# mid-fetch (or under minor clock skew) are not missed. Re-merges are idempotent.
DEFAULT_OVERLAP = timedelta(minutes=10)

# How old a persisted dataset's watermark may be before load_or_fetch refreshes it
# instead of reusing it. Matches the update-analytics CI cadence.
#
# Two staleness windows layer on the same dataset file, split across two levels:
# this 5-day *reuse* gate decides whether load_or_fetch calls its fetch_fn at
# all, and fetch_incremental's ~30-day *full_refresh_after* decides whether that
# fetch is a cheap since-delta or a full self-healing re-fetch. A normal run
# therefore reuses (<5d), refreshes incrementally (5-30d), or rebuilds (>30d).
DEFAULT_REUSE_MAX_AGE = timedelta(days=5)


# Dataset paths this process read or wrote — what "still live" means for
# pruning. Deliberately not file mtimes: `load_or_fetch` reuses a dataset
# without rewriting it for up to DEFAULT_REUSE_MAX_AGE, which is the refresh
# cadence itself, so a perfectly live dataset can go a whole run untouched on
# disk. Reading it still registers here.
_touched_datasets: set[Path] = set()

# How much of a file to inspect when deciding whether it is one of ours.
_DATASET_PREFIX_BYTES = 256


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


def prune_untouched_datasets(datasets_dir: Path | None = None) -> list[Path]:
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

    Note that "live" is relative to the configuration that ran: with
    ``GITHUB_EXTRA_ORGS`` unset, that org's datasets are genuinely unclaimed and
    will be removed, costing a full re-fetch if it is configured again later.
    Every deletion is logged for exactly this reason.
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
) -> None:
    """Atomically write the dataset and its two stamps to ``path`` as JSON.

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
    """
    _record_touch(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": DATASET_VERSION,
        # Ordered ahead of the records so both stamps stay inside the fixed
        # prefix `provenance` reads rather than parsing the whole file.
        "fetched_at": (fetched_at or datetime.now(UTC)).isoformat(),
        "fetched_through": fetched_through.isoformat(),
        "records": [serialize_record(record) for record in records],
    }
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


def load_dataset(path: Path, model_class: type[T]) -> tuple[list[T], datetime] | None:  # noqa: UP047
    """Load ``(records, fetched_through)``, or None if absent or incompatible."""
    # Before the existence check on purpose: a resource asking for this path is
    # what marks it live, whether or not a file is there yet. Every read route
    # (load_or_fetch's reuse, fetch_incremental's baseline) passes through here.
    _record_touch(path)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):  # fmt: skip
        return None
    if payload.get("version") != DATASET_VERSION:
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
    return records, fetched_through


def load_or_fetch(  # noqa: UP047
    resource: str,
    org: str,
    model_class: type[T],
    fetch_fn: Callable[[], list[T]],
    *,
    max_age: timedelta | None = DEFAULT_REUSE_MAX_AGE,
    fingerprint: str = "all",
) -> list[T]:
    """Reuse the persisted ``(resource, org)`` dataset if fresh enough, else build it.

    Wraps :func:`load_dataset` with a fetch fallback and consistent logging, so the
    runners don't each re-implement the reuse-or-fetch dance. ``fetch_fn`` produces
    the full record list when there is no usable dataset on disk, and is also called
    when the stored watermark is older than ``max_age`` — a standalone run therefore
    never silently serves arbitrarily old data. ``fetch_fn`` is normally an
    incremental fetcher, so a stale-triggered refresh only pulls the delta (and
    re-persists the dataset). ``max_age=None`` disables the staleness bound.

    ``fingerprint`` must match what ``fetch_fn`` writes (the incremental
    fetchers derive it from their query variables, e.g. issue states) — a
    mismatch would read one dataset while writing another.
    """
    state = load_dataset(dataset_path(resource, org, fingerprint), model_class)
    if state is not None:
        records, fetched_through = state
        if offline_mode_enabled():
            logger.info("Reusing offline %s/%s dataset (%d records)", org, resource, len(records))
            return records
        if fetched_through.tzinfo is None:
            fetched_through = fetched_through.replace(tzinfo=UTC)
        if max_age is None or fetched_through >= datetime.now(UTC) - max_age:
            logger.info("Reusing persisted %s/%s dataset (%d records)", org, resource, len(records))
            return records
        logger.info(
            "Persisted %s/%s dataset is stale (fetched through %s); refreshing",
            org,
            resource,
            fetched_through.isoformat(),
        )
        return fetch_fn()
    if offline_mode_enabled():
        raise OfflineDatasetMissingError(f"Offline mode requires a cached {resource}/{org} dataset")
    logger.info("No persisted %s/%s dataset; fetching from GitHub", org, resource)
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
    now: datetime | None = None,
) -> list[T]:
    """Fetch a resource incrementally, persisting the merged dataset.

    The first run (no stored dataset) does a full fetch. Subsequent runs fetch
    only records updated since ``watermark - overlap`` and merge them in. The new
    watermark is the latest ``updated_at`` across the merged set, falling back to
    the current time when no record carries one.

    Self-heal controls: ``force_full`` re-does a full fetch ignoring any stored
    dataset; ``full_refresh_after`` forces a full fetch when the stored watermark
    is older than that, bounding staleness and reclaiming deleted/missed records
    that an incremental ``since`` query can never see.

    Partial fetches: if ``full_fetch``/``since_fetch`` raise
    :class:`PartialOrgFetchError` (some repos failed even after retry), the records
    that *did* arrive are merged in, but the **watermark is held** at its prior
    value so the next run re-covers the gap. The one exception is a partial fetch
    on the very first run (no prior baseline): we refuse to persist an incomplete
    snapshot with an advanced watermark and re-raise instead.
    """
    current = now or datetime.now(UTC)
    state = load_dataset(path, model_class)
    if offline_mode_enabled():
        if state is None:
            raise OfflineDatasetMissingError(f"Offline mode requires a valid cached dataset at {path}")
        records, _ = state
        logger.info("Reusing offline dataset %s (%d records)", path, len(records))
        return records
    is_stale = full_refresh_after is not None and state is not None and state[1] < current - full_refresh_after
    held_watermark: datetime | None = None
    if state is None or force_full or is_stale:
        try:
            records = full_fetch()
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
    save_dataset(path, records, watermark, fetched_at=preserved_fetched_at)
    return records
