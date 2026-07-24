"""Declarative spec for the dashboard — one module per dashboard family.

Pure data consumed by the dashboard pipeline. Each family module declares its
chart macro plus the notes/methodology/wide-chart sets for its charts; the
contributors module also owns the table sections. This package assembles the
families in display order and exposes the same names the single-module spec
did, so consumers import from ``hiero_analytics.dashboard_spec`` unchanged.
"""

from __future__ import annotations

from hiero_analytics.dashboard_spec import community, contributors, onboarding, security

# Macro (family) display order.
_FAMILIES = (contributors, onboarding, security, community)

AFFILIATION_ISSUE_URL = contributors.AFFILIATION_ISSUE_URL
MACRO_NAME = contributors.MACRO_NAME
SECTION_SPECS = contributors.SECTION_SPECS
SECTION_GROUPS = contributors.SECTION_GROUPS
SECTION_ORDER = contributors.SECTION_ORDER
SECTION_GROUP_OF = contributors.SECTION_GROUP_OF
CHARTS_GROUP = "Charts"


def _canonical_macro(family_macro: dict) -> dict:
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


CHART_MACROS = [_canonical_macro(family.CHART_MACRO) for family in _FAMILIES]


def _merged(attribute: str) -> dict:
    """Merge a per-family dict, failing loudly if two families claim a chart."""
    merged: dict = {}
    for family in _FAMILIES:
        entries = getattr(family, attribute)
        overlap = merged.keys() & entries.keys()
        if overlap:
            raise ValueError(f"{attribute} defined by multiple families: {sorted(overlap)}")
        merged.update(entries)
    return merged


CHART_NOTES = _merged("CHART_NOTES")
CHART_METHODOLOGY = _merged("CHART_METHODOLOGY")
# Unlike the _merged() dicts above, WIDE_CHARTS is a plain union: it holds flags,
# so two families marking the same chart wide is redundant, not conflicting.
WIDE_CHARTS = set().union(*(family.WIDE_CHARTS for family in _FAMILIES))
