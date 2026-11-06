"""Column declaration and serialization for the dashboard spec.

A Column is the smallest unit the data API understands: it has a stable key,
a human label, an optional display format, and an optional prose description.

The column_spec() function is the single conversion point: it accepts either
plain tuples (as written by family modules) or Column instances, and always
emits a dict with key, label, and optional format/description fields.

This dual-shape design lets family modules keep using familiar tuple syntax
while the API and consumers always get a consistent object representation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Column:
    """A declared dashboard column: key, label, optional format, optional description."""

    key: str
    label: str
    format: str | None = None
    description: str | None = None

    # Tuple positions 0, 1, 2 are preserved, so a Column serialises exactly
    # like the legacy tuples (key, label, format) it replaces.
    def __init__(
        self,
        key: str,
        label: str,
        *,
        format: str | None = None,
        description: str | None = None,
    ) -> None:
        """Initialize a Column instance.

        Args:
            key: A stable key identifying the column.
            label: A human-readable label for the column.
            format: An optional display format string.
            description: An optional prose description.
        """
        object.__setattr__(self, "key", key)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "format", format)
        object.__setattr__(self, "description", description)


def _normalize_column(column: Any) -> Column:
    """Turn a column declaration into a Column.

    Accepts a Column (returned as is) or a 2-, 3-, or 4-element tuple/list of
    (key, label, format?, description?). Anything else raises, so callers only
    ever deal with one shape.
    """
    if isinstance(column, Column):
        return column
    if isinstance(column, (tuple, list)):
        if len(column) not in (2, 3, 4):
            raise ValueError(f"column declaration has {len(column)} elements; expected 2, 3, or 4")
        key, label, *rest = column
        format_ = rest[0] if len(rest) > 0 else None
        description = rest[1] if len(rest) > 1 else None
        return Column(key, label, format=format_, description=description)
    raise TypeError(f"expected a Column or a 2-/3-/4-element tuple, got {type(column).__name__}")


def column_spec(column: Any) -> dict[str, Any]:
    """Serialize a column declaration to the API's dict shape.

    Accepts either:
    - A 2-, 3-, or 4-element tuple: (key, label, format?, description?)
    - A Column instance

    Always returns a dict with:
        - key (str)   — always present
        - label (str) — always present
        - format (str) — only when the declaration included a format
        - description (str) — only when the declaration included a description
    """
    normalized = _normalize_column(column)
    spec: dict[str, Any] = {
        "key": normalized.key,
        "label": normalized.label,
    }
    if normalized.format:
        spec["format"] = normalized.format
    if normalized.description:
        spec["description"] = normalized.description
    return spec


def column_key(column: Any) -> str:
    """Return the stable key of a column declaration.

    Mirrors :func:`column_spec`: a ``Column`` instance exposes ``.key``
    directly, while tuple/list declarations carry it in position 0. Any other
    object exposing a ``key`` attribute is also accepted. This is the single
    normalizer callers should use instead of repeating the
    ``column.key if isinstance(column, Column) else column[0]`` idiom.
    """
    key = getattr(column, "key", None)
    if key is not None:
        return key
    if isinstance(column, (tuple, list)) and len(column) > 0:
        return column[0]
    raise TypeError(f"expected a Column or a non-empty tuple/list, got {type(column).__name__}")
