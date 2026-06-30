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
from collections.abc import Callable, Hashable, Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TypeVar

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


class PartialOrgFetchError(Exception):
    """Signals that an org-wide fetch could not cover every repository.

    Carries the records that *were* collected so the incremental store can merge
    them in while **holding the watermark** — the missed repos are then re-fetched
    on the next run instead of being silently skipped past (which would freeze
    them until the periodic full refresh).
    """

    def __init__(self, records: list, failed_repos: list | None = None) -> None:
        """Carry the records that arrived plus the repos still failing."""
        super().__init__(
            f"partial org fetch: {len(failed_repos or [])} repo(s) still failing"
        )
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


def save_dataset(path: Path, records: list[T], fetched_through: datetime) -> None:  # noqa: UP047
    """Atomically write the dataset and its watermark to ``path`` as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": DATASET_VERSION,
        "fetched_through": fetched_through.isoformat(),
        "records": [serialize_record(record) for record in records],
    }
    with NamedTemporaryFile(
        "w", dir=path.parent, delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(payload, tmp, indent=2, sort_keys=True)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def load_dataset(path: Path, model_class: type[T]) -> tuple[list[T], datetime] | None:  # noqa: UP047
    """Load ``(records, fetched_through)``, or None if absent or incompatible."""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
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
        records = [
            deserialize_record(model_class, record)
            for record in payload.get("records", [])
        ]
        fetched_through = datetime.fromisoformat(raw_through)
    except (TypeError, ValueError, KeyError, AttributeError):
        return None
    return records, fetched_through


def load_or_fetch(  # noqa: UP047
    resource: str,
    org: str,
    model_class: type[T],
    fetch_fn: Callable[[], list[T]],
) -> list[T]:
    """Reuse the persisted ``(resource, org)`` dataset if present, else build it.

    Wraps :func:`load_dataset` with a fetch fallback and consistent logging, so the
    runners don't each re-implement the reuse-or-fetch dance. ``fetch_fn`` produces
    the full record list when there is no usable dataset on disk.
    """
    state = load_dataset(dataset_path(resource, org, "all"), model_class)
    if state is not None:
        records, _ = state
        logger.info("Reusing persisted %s/%s dataset (%d records)", org, resource, len(records))
        return records
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
    is_stale = (
        full_refresh_after is not None
        and state is not None
        and state[1] < current - full_refresh_after
    )
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
    save_dataset(path, records, watermark)
    return records
