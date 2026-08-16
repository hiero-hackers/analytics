"""Tests for the client-side contributor activity heatmap view (#333)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from hiero_analytics.config import paths
from hiero_analytics.export import activity_views

ORG = "test-org"


@pytest.fixture(autouse=True)
def isolate_charts_dir(monkeypatch, tmp_path):
    """Point ORG_CHARTS_DIR at a sandbox, matching config/test_paths.py's pattern."""
    monkeypatch.setattr(paths, "ORG_CHARTS_DIR", tmp_path / "charts" / "org")


def _write_heatmap_csv(tmp_path: Path, rows: list[dict]) -> Path:
    """Write rows to the heatmap's expected source CSV filename in tmp_path."""
    pd.DataFrame(rows).to_csv(tmp_path / activity_views.SOURCE_CSV, index=False)
    return tmp_path


def _write_png(org: str) -> None:
    """Create an (empty, content doesn't matter) PNG at the path _png_fallback_path checks."""
    png_dir = paths.ORG_CHARTS_DIR / org
    png_dir.mkdir(parents=True, exist_ok=True)
    (png_dir / "contributor_activity_heatmap.png").write_bytes(b"")


def test_view_is_absent_without_data(tmp_path: Path):
    """An org with no heatmap data simply omits the view — no error."""
    assert activity_views.heatmap_view(ORG, tmp_path) is None
    assert activity_views.build_views(ORG, tmp_path) == []


def test_view_carries_rows_columns_and_values_matching_the_source(tmp_path: Path):
    """rows/columns/values line up with heatmap_chart_data's own output."""
    org_dir = _write_heatmap_csv(
        tmp_path,
        [
            {"contributor name": "alice", "role": "Maintainer", "activity score": 12, "2026-01": 8, "2026-02": 4},
            {"contributor name": "bob", "role": "Committer", "activity score": 5, "2026-01": 2, "2026-02": 3},
        ],
    )

    view = activity_views.heatmap_view(ORG, org_dir)

    assert view is not None
    assert view["rows"] == ["alice", "bob"]
    assert view["columns"] == ["2026-01", "2026-02"]
    assert view["values"] == [[8.0, 4.0], [2.0, 3.0]]


def test_max_value_is_the_single_highest_cell(tmp_path: Path):
    """max_value drives continuous colour interpolation, not a fixed bucket count."""
    org_dir = _write_heatmap_csv(
        tmp_path,
        [
            {"contributor name": "alice", "role": "Maintainer", "activity score": 20, "2026-01": 20, "2026-02": 1},
            {"contributor name": "bob", "role": "Committer", "activity score": 9, "2026-01": 3, "2026-02": 6},
        ],
    )

    view = activity_views.heatmap_view(ORG, org_dir)

    assert view["max_value"] == 20.0


def test_png_fallback_is_none_when_the_png_was_never_produced(tmp_path: Path):
    """A view without a corresponding PNG on disk must not link to a 404."""
    org_dir = _write_heatmap_csv(
        tmp_path,
        [{"contributor name": "alice", "role": "Maintainer", "activity score": 4, "2026-01": 4}],
    )
    # Deliberately not calling _write_png(ORG) — the PNG doesn't exist.

    view = activity_views.heatmap_view(ORG, org_dir)

    assert view["png_fallback"] is None


def test_png_fallback_matches_the_chart_apis_path_format_when_the_png_exists(tmp_path: Path):
    """When the PNG genuinely exists, the path shape must match _chart_variant's format.

    So chartUrl() works unmodified.
    """
    org_dir = _write_heatmap_csv(
        tmp_path,
        [{"contributor name": "alice", "role": "Maintainer", "activity score": 4, "2026-01": 4}],
    )
    _write_png(ORG)

    view = activity_views.heatmap_view(ORG, org_dir)

    assert view["png_fallback"] == f"charts/org/{ORG}/contributor_activity_heatmap.png"


def test_values_are_plain_floats_not_numpy_scalars(tmp_path: Path):
    """JSON serialization requires plain python types, not numpy.float64."""
    org_dir = _write_heatmap_csv(
        tmp_path,
        [{"contributor name": "alice", "role": "Maintainer", "activity score": 4, "2026-01": 4}],
    )

    view = activity_views.heatmap_view(ORG, org_dir)

    assert all(isinstance(cell, float) for row in view["values"] for cell in row)
    assert isinstance(view["max_value"], float)


def test_build_views_returns_a_single_heatmap_view(tmp_path: Path):
    """This family's bespoke views list — one heatmap view when there's data."""
    org_dir = _write_heatmap_csv(
        tmp_path,
        [{"contributor name": "alice", "role": "Maintainer", "activity score": 4, "2026-01": 4}],
    )

    views = activity_views.build_views(ORG, org_dir)

    assert [view["id"] for view in views] == [activity_views.VIEW_ID]
    assert views[0]["kind"] == "heatmap"
