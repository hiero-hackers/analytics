"""File-backed cache helpers for normalized GitHub data records."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TypeVar

from hiero_analytics.config.paths import OUTPUTS_DIR

from .models import (
    ContributorActivityRecord,
    IssueRecord,
    PullRequestDifficultyRecord,
    RepositoryRecord,
    CodeOwnersRecord,
    RunnerRecord,
)

logger = logging.getLogger(__name__)

CACHE_VERSION = 1
DEFAULT_GITHUB_CACHE_TTL_SECONDS = 60*60*24 # 24 hours
GITHUB_CACHE_DIR = OUTPUTS_DIR / "cache" / "github"

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
_DATETIME_FIELDS: dict[type[object], tuple[str, ...]] = {
    RepositoryRecord: ("created_at",),
    IssueRecord: ("created_at", "closed_at"),
    PullRequestDifficultyRecord: ("pr_created_at", "pr_merged_at"),
    ContributorActivityRecord: ("occurred_at",),
    CodeOwnersRecord: (),
    RunnerRecord: (),
}
RecordType = TypeVar(
    "RecordType",
    RepositoryRecord,
    IssueRecord,
    PullRequestDifficultyRecord,
    ContributorActivityRecord,
)


def _env_bool(name: str, default: bool) -> bool:
    """Parse a boolean environment variable with a safe fallback."""
    value = os.getenv(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    return default


def _env_int(name: str, default: int) -> int:
    """Parse an integer environment variable with a safe fallback."""
    value = os.getenv(name)
    if value is None:
        return default

    try:
        return int(value.strip())
    except ValueError:
        return default


def _cache_enabled(use_cache: bool | None) -> bool:
    """Resolve whether cache reads and writes are enabled."""
    if use_cache is not None:
        return use_cache
    return _env_bool("GITHUB_CACHE_ENABLED", True)


def _cache_ttl_seconds(ttl_seconds: int | None) -> int:
    """Resolve the effective cache TTL in seconds."""
    if ttl_seconds is not None:
        return ttl_seconds
    return _env_int(
        "GITHUB_CACHE_TTL_SECONDS",
        DEFAULT_GITHUB_CACHE_TTL_SECONDS,
    )


def _slugify(value: str) -> str:
    """Convert a cache scope string into a filesystem-safe slug."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")
    return slug or "cache"


def _serialize_value(value: object) -> object:
    """Convert dataclass payload values into JSON-compatible values."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize_value(item) for key, item in value.items()}
    return value


# PEP 695 type parameters are intentionally avoided here because the package
# supports Python 3.11.
def _serialize_record(  # noqa: UP047
    record: RecordType,
) -> dict[str, object]:
    """Serialize a normalized record into a JSON-compatible mapping."""
    payload = asdict(record)
    return {key: _serialize_value(value) for key, value in payload.items()}


def _deserialize_record(  # noqa: UP047
    record_type: type[RecordType],
    payload: dict[str, object],
) -> RecordType:
    """Deserialize a record payload from JSON back into a dataclass."""
    restored = dict(payload)

    for field_name in _DATETIME_FIELDS[record_type]:
        raw_value = restored.get(field_name)
        if raw_value is not None:
            restored[field_name] = datetime.fromisoformat(str(raw_value))

    return record_type(**restored)  # type: ignore[arg-type]


def _normalize_cached_at(cached_at: datetime) -> datetime:
    """Ensure cached timestamps are offset-aware and normalized to UTC."""
    if cached_at.tzinfo is None:
        return cached_at.replace(tzinfo=timezone.utc)
    return cached_at.astimezone(timezone.utc)


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
        age_seconds = (datetime.now(timezone.utc) - cached_at).total_seconds()
        if age_seconds > effective_ttl_seconds:
            logger.info("Cache entry is stale for %s (%s)", kind, scope)
            return None

    records_payload = payload.get("records")
    if not isinstance(records_payload, list):
        logger.info("Ignoring cache file with invalid record payload: %s", cache_path)
        return None

    logger.info("Cache hit for %s (%s)", kind, scope)
    return [
        _deserialize_record(record_type, dict(record_payload))
        for record_payload in records_payload
        if isinstance(record_payload, dict)
    ]


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
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "records": [_serialize_record(record) for record in records],
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
            json.dump(payload, temp_file, indent=2, sort_keys=True)
            temp_file.write("\n")

        os.replace(temp_path, cache_path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise

    logger.info("Cached %d records for %s (%s)", len(records), kind, scope)
