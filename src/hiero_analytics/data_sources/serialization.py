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
    return tuple(
        field.name
        for field in fields(record_type)
        if annotation_is_datetime(hints.get(field.name))
    )


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
    """Deserialize a record payload from JSON back into a dataclass."""
    restored = dict(payload)

    for field_name in datetime_fields(record_type):
        raw_value = restored.get(field_name)
        if raw_value is not None:
            restored[field_name] = datetime.fromisoformat(str(raw_value))

    return record_type(**restored)  # type: ignore[arg-type]
