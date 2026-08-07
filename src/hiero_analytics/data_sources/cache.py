"""File-backed cache helpers for normalized GitHub data records.

Freshness is governed by ``GITHUB_CACHE_TTL_SECONDS`` or the
``ttl_seconds`` override. A positive value expires cache entries older
than the configured number of seconds. A value of ``0`` or less
disables expiry and keeps cache entries indefinitely until the cache
directory is cleared manually. This behavior is intended as an explicit
"cache forever" mode (for example, during offline debugging).

Because an empty or invalid environment variable also resolves to
``0``, the cache logs a warning when non-positive TTL mode is active so
the configuration is explicit and visible.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TypeVar

from hiero_analytics.config.env import env_bool, env_int
from hiero_analytics.config.paths import OUTPUTS_DIR

from .serialization import deserialize_record, serialize_record

logger = logging.getLogger(__name__)

CACHE_VERSION = 1
DEFAULT_GITHUB_CACHE_TTL_SECONDS = 60 * 60 * 24 * 14  # 14 days
GITHUB_CACHE_DIR = OUTPUTS_DIR / "cache" / "github"


RecordType = TypeVar("RecordType")


def _cache_enabled(use_cache: bool | None) -> bool:
    """Resolve whether cache reads and writes are enabled."""
    if use_cache is not None:
        return use_cache
    return env_bool("GITHUB_CACHE_ENABLED", True)


def _cache_ttl_seconds(ttl_seconds: int | None) -> int:
    """Resolve the effective cache TTL in seconds.

    A resolved value of ``0`` or less disables cache expiry (see the module
    docstring). Because an empty or invalid ``GITHUB_CACHE_TTL_SECONDS`` value
    can also resolve to ``0``, a warning is logged whenever non-positive TTL
    mode is active.
    """
    if ttl_seconds is not None:
        resolved = ttl_seconds
    else:
        resolved = env_int(
            "GITHUB_CACHE_TTL_SECONDS",
            DEFAULT_GITHUB_CACHE_TTL_SECONDS,
        )

    if resolved <= 0:
        logger.warning(
            "Cache TTL resolved to %d (<=0); cache expiry is disabled. "
            "Entries will remain until the cache directory is cleared manually.",
            resolved,
        )

    return resolved


def _slugify(value: str) -> str:
    """Convert a cache scope string into a filesystem-safe slug."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")
    return slug or "cache"


def _normalize_cached_at(cached_at: datetime) -> datetime:
    """Ensure cached timestamps are offset-aware and normalized to UTC."""
    if cached_at.tzinfo is None:
        return cached_at.replace(tzinfo=UTC)
    return cached_at.astimezone(UTC)


def _cache_path(
    kind: str,
    scope: str,
    parameters: dict[str, object],
) -> Path:
    """Build a stable path for a cached fetch payload."""
    fingerprint = hashlib.sha256(
        json.dumps(parameters, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]

    return GITHUB_CACHE_DIR / f"{kind}_{_slugify(scope)}_{fingerprint}.json"


def load_records_cache(  # noqa: UP047
    kind: str,
    scope: str,
    parameters: dict[str, object],
    record_type: type[RecordType],
    *,
    use_cache: bool | None = None,
    ttl_seconds: int | None = None,
    refresh: bool = False,
) -> list[RecordType] | None:
    """Load cached normalized records when a valid cache entry exists."""
    if not _cache_enabled(use_cache):
        return None

    cache_path = _cache_path(kind, scope, parameters)
    if refresh or not cache_path.exists():
        return None

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Ignoring unreadable cache file %s: %s", cache_path, exc)
        return None

    if payload.get("version") != CACHE_VERSION:
        logger.info("Ignoring cache file with unexpected version: %s", cache_path)
        return None

    if payload.get("record_type") != record_type.__name__:
        logger.info("Ignoring cache file with unexpected record type: %s", cache_path)
        return None

    # Echo the stored parameters back instead of trusting the 48-bit filename
    # fingerprint alone — a hash collision would otherwise serve the wrong dataset.
    stored_parameters = json.loads(json.dumps(parameters))  # normalize like the saved payload
    if payload.get("parameters") != stored_parameters:
        logger.info("Ignoring cache file with mismatched parameters: %s", cache_path)
        return None

    cached_at_raw = payload.get("cached_at")
    if not isinstance(cached_at_raw, str):
        logger.info("Ignoring cache file with missing timestamp: %s", cache_path)
        return None

    try:
        cached_at = _normalize_cached_at(datetime.fromisoformat(cached_at_raw))
    except ValueError:
        logger.info("Ignoring cache file with invalid timestamp: %s", cache_path)
        return None

    effective_ttl_seconds = _cache_ttl_seconds(ttl_seconds)
    if effective_ttl_seconds > 0:
        age_seconds = (datetime.now(UTC) - cached_at).total_seconds()
        if age_seconds > effective_ttl_seconds:
            logger.info("Cache entry is stale for %s (%s)", kind, scope)
            return None

    records_payload = payload.get("records")
    if not isinstance(records_payload, list):
        logger.info("Ignoring cache file with invalid record payload: %s", cache_path)
        return None

    # A record shape that no longer matches the dataclass (field added/renamed
    # without a CACHE_VERSION bump) is a cache miss, not a crash — the caller
    # re-fetches and overwrites the stale file.
    try:
        records = [
            deserialize_record(record_type, dict(record_payload))
            for record_payload in records_payload
            if isinstance(record_payload, dict)
        ]
    except (TypeError, ValueError, KeyError, AttributeError):
        logger.warning("Ignoring cache file with incompatible record shape: %s", cache_path)
        return None

    logger.info("Cache hit for %s (%s)", kind, scope)
    return records


def save_records_cache(  # noqa: UP047
    kind: str,
    scope: str,
    parameters: dict[str, object],
    record_type: type[RecordType],
    records: list[RecordType],
    *,
    use_cache: bool | None = None,
) -> None:
    """Persist normalized records to the on-disk cache."""
    if not _cache_enabled(use_cache):
        return

    cache_path = _cache_path(kind, scope, parameters)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "version": CACHE_VERSION,
        "kind": kind,
        "scope": scope,
        "parameters": parameters,
        "record_type": record_type.__name__,
        "cached_at": datetime.now(UTC).isoformat(),
        "records": [serialize_record(record) for record in records],
    }

    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=cache_path.parent,
            prefix=f"{cache_path.stem}_",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            # Compact separators: cache files are machine-read only.
            json.dump(payload, temp_file, separators=(",", ":"))
            temp_file.write("\n")

        os.replace(temp_path, cache_path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise

    logger.info("Cached %d records for %s (%s)", len(records), kind, scope)
