"""(De)serialization of normalized dataclass records to and from JSON.

Shared by the TTL cache (``cache.py``) and the durable dataset store
(``dataset_store.py``). Datetime fields are derived from each record's type
hints, so any datetime field round-trips correctly with no hand-maintained
registry to drift out of sync.
"""

from __future__ import annotations

from dataclasses import asdict, fields
from datetime import datetime
from functools import cache
from typing import TypeVar, get_args, get_type_hints

T = TypeVar("T")


def parse_github_datetime(value: object, *, strict: bool = False) -> datetime | None:
    """Parse a GitHub ISO-8601 timestamp (trailing ``Z`` normalized to UTC).

    Missing or non-string input returns None. Malformed strings also return
    None, unless ``strict`` — for payloads where a bad timestamp means a broken
    response rather than an absent optional field — in which case the
    ``ValueError`` propagates.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        if strict:
            raise
        return None


def annotation_is_datetime(annotation: object) -> bool:
    """True for a resolved annotation of ``datetime`` or ``datetime | None``."""
    return annotation is datetime or datetime in get_args(annotation)


@cache
def datetime_fields(record_type: type) -> tuple[str, ...]:
    """Names of a record's datetime fields, derived from its type hints.

    Every ``datetime`` (or ``datetime | None``) field on a record dataclass is
    discovered automatically, so adding a new datetime field can never silently
    break round-tripping. Cached per type since record schemas are fixed.
    """
    hints = get_type_hints(record_type)
    return tuple(field.name for field in fields(record_type) if annotation_is_datetime(hints.get(field.name)))


@cache
def _required_datetime_fields(record_type: type) -> tuple[str, ...]:
    """Names of a record's non-optional datetime fields (hint is exactly ``datetime``)."""
    hints = get_type_hints(record_type)
    return tuple(field.name for field in fields(record_type) if hints.get(field.name) is datetime)


def serialize_value(value: object) -> object:
    """Convert dataclass payload values into JSON-compatible values."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: serialize_value(item) for key, item in value.items()}
    return value


def serialize_record(record: T) -> dict[str, object]:  # noqa: UP047
    """Serialize a normalized record into a JSON-compatible mapping."""
    payload = asdict(record)
    return {key: serialize_value(value) for key, value in payload.items()}


def deserialize_record(record_type: type[T], payload: dict[str, object]) -> T:  # noqa: UP047
    """Deserialize a record payload from JSON back into a dataclass.

    Raises ``ValueError`` when a non-optional datetime field comes back null —
    frozen dataclasses validate nothing themselves, so this is the one place a
    corrupted payload can be rejected before it flows into analyses. Cache and
    dataset loaders catch the error and treat the file as a miss.
    """
    restored = dict(payload)

    for field_name in datetime_fields(record_type):
        raw_value = restored.get(field_name)
        if raw_value is not None:
            restored[field_name] = parse_github_datetime(str(raw_value), strict=True)

    record = record_type(**restored)  # type: ignore[arg-type]

    for field_name in _required_datetime_fields(record_type):
        if not isinstance(getattr(record, field_name), datetime):
            raise ValueError(
                f"{record_type.__name__}.{field_name} must be a datetime, got {getattr(record, field_name)!r}"
            )
    return record
