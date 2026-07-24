"""Declarative spec for the dashboard — one module per dashboard family.

Pure data consumed by the dashboard pipeline. Each family module declares its
chart macro plus the notes/methodology/wide-chart sets for its charts; the
contributors module also owns the table sections. This package assembles the
families in display order (helpers in ``_assembly``) and exposes the same
names the single-module spec did, so consumers import from
``hiero_analytics.dashboard_spec`` unchanged.
"""

from __future__ import annotations

from hiero_analytics.dashboard_spec import community, contributors, onboarding, security
from hiero_analytics.dashboard_spec._assembly import canonical_macro, merged

# Macro (family) display order.
_FAMILIES = (contributors, onboarding, security, community)

AFFILIATION_ISSUE_URL = contributors.AFFILIATION_ISSUE_URL
MACRO_NAME = contributors.MACRO_NAME
SECTION_SPECS = contributors.SECTION_SPECS
SECTION_GROUPS = contributors.SECTION_GROUPS
SECTION_ORDER = contributors.SECTION_ORDER
SECTION_GROUP_OF = contributors.SECTION_GROUP_OF
CHARTS_GROUP = "Charts"

CHART_MACROS = [canonical_macro(family.CHART_MACRO) for family in _FAMILIES]
CHART_NOTES = merged(_FAMILIES, "CHART_NOTES")
CHART_METHODOLOGY = merged(_FAMILIES, "CHART_METHODOLOGY")
# Unlike the merged() dicts above, WIDE_CHARTS is a plain union: it holds flags,
# so two families marking the same chart wide is redundant, not conflicting.
WIDE_CHARTS = set().union(*(family.WIDE_CHARTS for family in _FAMILIES))
