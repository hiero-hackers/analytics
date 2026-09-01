"""Declarative spec for the dashboard — one module per dashboard family.

Pure data consumed by the dashboard pipeline. Each family module declares its
chart macro plus the notes/methodology/wide-chart sets for its charts; a
family with table sections (contributors, governance) also declares
``SECTION_SPECS``/``SECTION_GROUPS``. This package assembles the families in
display order (helpers in ``_assembly``) and exposes the table-bearing
families per macro name, so the dashboard pipeline renders each family's
tables inside its own macro.
"""

from __future__ import annotations

from hiero_analytics.dashboard_spec import (
    community,
    constants,
    contributors,
    governance,
    hips,
    onboarding,
    security,
)
from hiero_analytics.dashboard_spec._assembly import canonical_macro, merged, table_variants
from hiero_analytics.dashboard_spec.metrics import METRIC_ANNOTATIONS

# Macro (family) display order — the tab order the dashboard shows.
_FAMILIES = (contributors, governance, hips, security, onboarding, community)

# The assembled spec surface — everything a consumer (the data API emitter,
# the contract tests) reads off this package.
__all__ = [
    "AFFILIATION_ISSUE_URL",
    "CHART_MACROS",
    "CHART_METHODOLOGY",
    "CHART_NOTES",
    "COLUMN_FORMATS",
    "CUSTOM_VIEW_MODULES",
    "LIVE_VIEW_IDS",
    "MACRO_ABSENT_NOTES",
    "MACRO_GLOSSARIES",
    "MACRO_GROUP_ORDER",
    "MACRO_PARENTS",
    "METRIC_ANNOTATIONS",
    "PROJECT_ISSUES_URL",
    "TABLE_FAMILIES",
    "WIDE_CHARTS",
    "table_variants",
]

AFFILIATION_ISSUE_URL = governance.AFFILIATION_ISSUE_URL
PROJECT_ISSUES_URL = constants.PROJECT_ISSUES_URL

# Display formats a section column may declare, as the third tuple element.
# The frontend implements exactly these (web/src/components/FormattedCell.tsx);
# an unlisted value would fall through to plain text, so a typo is caught by
# tests/dashboard_spec instead of shipping as a silently unformatted column.
COLUMN_FORMATS = frozenset({"hip", "date", "link", "evidence", "status", "flag", "presence", "number"})

# The families that carry table sections, keyed by their macro name — the
# dashboard pipeline reads SECTION_SPECS / SECTION_ORDER / SECTION_GROUP_OF
# off each. A family without tables simply isn't listed.
TABLE_FAMILIES = {family.CHART_MACRO["name"]: family for family in _FAMILIES if hasattr(family, "SECTION_SPECS")}

# Families whose view needs more than tables and chart galleries name a module
# exposing ``build_views(org, org_data_dir)``; the data API imports it the same
# way the pipeline registry resolves a pipeline module.
CUSTOM_VIEW_MODULES = {
    family.CHART_MACRO["name"]: family.CUSTOM_VIEWS_MODULE
    for family in _FAMILIES
    if hasattr(family, "CUSTOM_VIEWS_MODULE")
}

# A family may replace the shared column glossary with its own "how to read
# this" explainer; the rest fall back to the shared one.
MACRO_GLOSSARIES = {family.CHART_MACRO["name"]: family.GLOSSARY for family in _FAMILIES if hasattr(family, "GLOSSARY")}

# Families that render as sub-tabs of an umbrella tab, macro name -> umbrella
# name. The frontend shows one top-level tab per umbrella and a second tab row
# for its members; a family without MACRO_PARENT is a top-level tab itself.
MACRO_PARENTS = {
    family.CHART_MACRO["name"]: family.MACRO_PARENT for family in _FAMILIES if hasattr(family, "MACRO_PARENT")
}

# Why a tab may have no content for an org (no governance config, ledger-only
# process, pipelines not yet enabled). The frontend shows this instead of a
# blank tab, so absence reads as a property of the data rather than a bug.
MACRO_ABSENT_NOTES = {
    family.CHART_MACRO["name"]: family.ABSENT_NOTE for family in _FAMILIES if hasattr(family, "ABSENT_NOTE")
}


def _group_order(family) -> list[str]:
    """The family's section-group display order, chart-only groups included.

    SECTION_GROUPS is authoritative (it may list chart-only groups as empty
    entries to place them); any chart card whose group it doesn't mention is
    appended in card order, so nothing renders unplaced.
    """
    names = [name for name, _ids in getattr(family, "SECTION_GROUPS", [])]
    for specs in family.CHART_MACRO["charts"].values():
        for spec in specs:
            group = spec.get("group") or spec["title"]
            if group not in names:
                names.append(group)
    return names


# Macro name -> ordered section-group names. The frontend renders each tab as
# this sequence of named sections (views + chart cards + tables that share the
# group name), with the jump bar linking each one — there is no generic
# "Charts" section.
MACRO_GROUP_ORDER = {family.CHART_MACRO["name"]: _group_order(family) for family in _FAMILIES}

CHART_MACROS = [canonical_macro(family.CHART_MACRO) for family in _FAMILIES]
CHART_NOTES = merged(_FAMILIES, "CHART_NOTES")
CHART_METHODOLOGY = merged(_FAMILIES, "CHART_METHODOLOGY")
LIVE_VIEW_IDS = merged(_FAMILIES, "LIVE_VIEW_IDS")
# Unlike the merged() dicts above, WIDE_CHARTS is a plain union: it holds flags,
# so two families marking the same chart wide is redundant, not conflicting.
WIDE_CHARTS = set().union(*(family.WIDE_CHARTS for family in _FAMILIES))
