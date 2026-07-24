"""Assembly helpers for the dashboard-spec package.

Pure functions used by the package ``__init__`` to canonicalise each family's
chart macro and merge the per-family dicts, kept here so the ``__init__``
reads as declarative assembly only.
"""

from __future__ import annotations

from collections.abc import Sequence
from types import ModuleType


def canonical_macro(family_macro: dict) -> dict:
    """Canonicalize a family's chart macro for consumers.

    Every ``files`` entry becomes ``(caption, [(label, filename), ...])``;
    family modules may write a bare filename as sugar for a single variant.
    """
    charts = {
        org: [
            {
                **spec,
                "files": [
                    (caption, [(caption, target)] if isinstance(target, str) else list(target))
                    for caption, target in spec["files"]
                ],
            }
            for spec in specs
        ]
        for org, specs in family_macro["charts"].items()
    }
    return {**family_macro, "charts": charts}


def merged(families: Sequence[ModuleType], attribute: str) -> dict:
    """Merge a per-family dict, failing loudly if two families claim a chart."""
    result: dict = {}
    for family in families:
        entries = getattr(family, attribute)
        overlap = result.keys() & entries.keys()
        if overlap:
            raise ValueError(f"{attribute} defined by multiple families: {sorted(overlap)}")
        result.update(entries)
    return result
