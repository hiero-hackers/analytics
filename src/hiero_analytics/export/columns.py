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
    if isinstance(column, Column):
        key, label, format_, description = (
            column.key,
            column.label,
            column.format,
            column.description,
        )
    elif isinstance(column, (tuple, list)):
        if len(column) == 2:
            key, label, format_, description = column[0], column[1], None, None
        elif len(column) == 3:
            key, label, format_ = column[0], column[1], column[2]
            description = None
        elif len(column) == 4:
            key, label, format_, description = column[0], column[1], column[2], column[3]
        else:
            raise ValueError(f"column declaration has {len(column)} elements; expected 2, 3, or 4")
    else:
        raise TypeError(f"expected a Column or a 2-/3-/4-element tuple, got {type(column).__name__}")

    spec: dict[str, Any] = {
        "key": key,
        "label": label,
    }
    if format_:
        spec["format"] = format_
    if description:
        spec["description"] = description
    return spec
