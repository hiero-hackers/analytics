"""Contributor activity views the dashboard renders client-side.

Pure data assembly, mirroring ``export/hip_views.py``: reads the persisted
heatmap dataset and returns a document the web dashboard fetches and renders
live, instead of a matplotlib PNG. Named ``activity_views`` (not
``contributor_heatmap_views``) so the team/org/repo heatmap variants can join
this module later without a rename.

Colour is deliberately not shipped here: values are unbounded and grow with
community activity, so the frontend interpolates continuously between its own
``--heat-*`` CSS tokens using the ``max_value`` this module provides, rather
than being handed a fixed bucket count that loses resolution over time.
"""

from __future__ import annotations

from pathlib import Path

from hiero_analytics.analysis.contributor_heatmap import heatmap_chart_data
from hiero_analytics.config import paths
from hiero_analytics.export.artifacts import load_csv

VIEW_ID = "contributor-activity-heatmap"
TITLE = "Contributor activity heatmap"
DESCRIPTION = (
    "Weighted monthly activity for the most active contributors over the last six months. "
    "Rendered live from the underlying data — hover a cell for its exact value."
)
SOURCE_CSV = "contributor_activity_heatmap.csv"
# Matches the path format `_chart_variant` in export/data_api.py already builds for
# this same PNG, so the frontend can hand this straight to `chartUrl()` without
# reconstructing the path itself.
_PNG_FILENAME = "contributor_activity_heatmap.png"


def _png_fallback_path(org: str) -> str | None:
    """The PNG this view supersedes, in the same path shape the chart API uses.

    None if that PNG was never actually produced — a linked-to fallback that
    404s is worse than no link at all. This is the same existence check
    export/data_api.py's _org_chart_sections already does per variant; done
    here too so a frontend link built from this field is never dead on arrival.
    """
    if not (paths.ORG_CHARTS_DIR / org / _PNG_FILENAME).exists():
        return None
    return f"charts/org/{org}/{_PNG_FILENAME}"


def heatmap_view(org: str, org_data_dir: Path) -> dict | None:
    """The contributor heatmap as a view document, or None without data."""
    heatmap_df = load_csv(org_data_dir / SOURCE_CSV)
    chart = heatmap_chart_data(heatmap_df)
    if chart is None:
        return None
    values, row_labels, col_labels = chart

    # Flat list of every cell's value, since values may be a numpy array —
    # keep the JSON plain floats, not numpy scalars.
    flat_values = [[float(cell) for cell in row] for row in values]
    max_value = max((cell for row in flat_values for cell in row), default=0.0)

    return {
        "id": VIEW_ID,
        "kind": "heatmap",
        "title": TITLE,
        "description": DESCRIPTION,
        "badge": f"{len(row_labels)} contributors",
        "source": SOURCE_CSV,
        "rows": row_labels,
        "columns": col_labels,
        "values": flat_values,
        "max_value": max_value,
        "png_fallback": _png_fallback_path(org),
    }


def build_views(org: str, org_data_dir: Path) -> list[dict]:
    """This family's bespoke views. Empty when there's no heatmap data for the org."""
    view = heatmap_view(org, org_data_dir)
    return [view] if view is not None else []
