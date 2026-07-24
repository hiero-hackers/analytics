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

from hiero_analytics.dashboard_spec import community, contributors, governance, onboarding, security
from hiero_analytics.dashboard_spec._assembly import canonical_macro, merged

# Macro (family) display order.
_FAMILIES = (contributors, governance, onboarding, security, community)

AFFILIATION_ISSUE_URL = governance.AFFILIATION_ISSUE_URL
CHARTS_GROUP = "Charts"

# The families that carry table sections, keyed by their macro name — the
# dashboard pipeline reads SECTION_SPECS / SECTION_ORDER / SECTION_GROUP_OF
# off each. A family without tables simply isn't listed.
TABLE_FAMILIES = {family.CHART_MACRO["name"]: family for family in _FAMILIES if hasattr(family, "SECTION_SPECS")}

CHART_MACROS = [canonical_macro(family.CHART_MACRO) for family in _FAMILIES]
CHART_NOTES = merged(_FAMILIES, "CHART_NOTES")
CHART_METHODOLOGY = merged(_FAMILIES, "CHART_METHODOLOGY")
# Unlike the merged() dicts above, WIDE_CHARTS is a plain union: it holds flags,
# so two families marking the same chart wide is redundant, not conflicting.
WIDE_CHARTS = set().union(*(family.WIDE_CHARTS for family in _FAMILIES))
