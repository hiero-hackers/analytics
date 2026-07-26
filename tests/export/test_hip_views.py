"""Tests for the HIP bespoke views (coverage matrix, governance board)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from hiero_analytics.export import hip_views

ORG = "test-org"
R = "test-org/"

COMPONENTS = [
    (f"{R}consensus", "consensus", "Services"),
    (f"{R}mirror", "mirror", "Services"),
    (f"{R}sdk-java", "java", "SDKs"),
    (f"{R}sdk-go", "go", "SDKs"),
    (f"{R}relay", "relay", "Tooling & clients"),
]


@pytest.fixture
def hip_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A spec inventory and activity exercising every cell and gap state."""
    monkeypatch.setattr(hip_views.hips_spec, "MATRIX_COMPONENTS", {ORG: COMPONENTS})
    pd.DataFrame(
        [
            {"hip": 300, "hip_title": "Hot spec", "hip_status": "Approved"},
            {"hip": 200, "hip_title": "Complete spec", "hip_status": "Final"},
            {"hip": 150, "hip_title": "Services only", "hip_status": "Accepted"},
            {"hip": 100, "hip_title": "Open only", "hip_status": "Review"},
            {"hip": 50, "hip_title": "Untouched", "hip_status": "Deferred"},
            {"hip": 10, "hip_title": "Odd one", "hip_status": "Bikeshedding"},
        ]
    ).to_csv(tmp_path / "hip_summary.csv", index=False)
    pd.DataFrame(
        [
            {"hip": 300, "repo": f"{R}consensus", "merged_prs": 30, "open_prs": 2},
            {"hip": 300, "repo": f"{R}sdk-java", "merged_prs": 3, "open_prs": 0},
            {"hip": 200, "repo": f"{R}sdk-java", "merged_prs": 1, "open_prs": 0},
            {"hip": 200, "repo": f"{R}sdk-go", "merged_prs": 2, "open_prs": 0},
            {"hip": 150, "repo": f"{R}mirror", "merged_prs": 4, "open_prs": 0},
            {"hip": 100, "repo": f"{R}consensus", "merged_prs": 0, "open_prs": 5},
        ]
    ).to_csv(tmp_path / "hip_repo_activity.csv", index=False)
    return tmp_path


def _row(matrix: dict, hip: int) -> dict:
    return next(row for row in matrix["rows"] if row["key"] == hip)


def test_rows_are_ordered_by_heat_with_untouched_specs_last(hip_data: Path):
    """Most referencing activity first; blank specs sink but stay visible."""
    matrix = hip_views.coverage_matrix(ORG, hip_data)

    assert [row["key"] for row in matrix["rows"]] == [300, 100, 150, 200, 50, 10]


def test_cells_carry_merged_and_open_counts(hip_data: Path):
    """Each cell reports both counts; the frontend picks the display state."""
    cells = {cell["key"]: cell for cell in _row(hip_views.coverage_matrix(ORG, hip_data), 300)["cells"]}

    assert cells[f"{R}consensus"] == {"key": f"{R}consensus", "merged": 30, "open": 2}
    assert cells[f"{R}relay"] == {"key": f"{R}relay", "merged": 0, "open": 0}


def test_gap_note_covers_every_state(hip_data: Path):
    """Complete, partial, no-SDK-activity, and nothing-anywhere read distinctly."""
    matrix = hip_views.coverage_matrix(ORG, hip_data)

    assert _row(matrix, 200)["note"] == {"kind": "complete", "text": "✓ all SDKs"}
    assert _row(matrix, 300)["note"]["kind"] == "partial"
    assert _row(matrix, 300)["note"]["items"] == ["go"]
    # Services activity but no SDK PRs — the SDKs are genuinely the gap.
    assert _row(matrix, 150)["note"] == {"kind": "none", "text": "no SDK activity found"}
    # Nothing anywhere shouldn't single out the SDKs.
    assert _row(matrix, 50)["note"] == {"kind": "none", "text": "no activity found"}


def test_open_only_row_is_not_reported_as_no_activity(hip_data: Path):
    """An open-PR-only spec has activity, so its gap note names the SDKs."""
    assert _row(hip_views.coverage_matrix(ORG, hip_data), 100)["note"]["text"] == "no SDK activity found"


def test_bands_group_consecutive_components(hip_data: Path):
    """Header bands span their components in first-appearance order."""
    matrix = hip_views.coverage_matrix(ORG, hip_data)

    assert matrix["bands"] == [
        {"label": "Services", "span": 2},
        {"label": "SDKs", "span": 2},
        {"label": "Tooling & clients", "span": 1},
    ]


def test_filters_are_present_statuses_most_ready_first(hip_data: Path):
    """Governance pills follow the readiness order; unknown statuses trail."""
    matrix = hip_views.coverage_matrix(ORG, hip_data)

    assert matrix["filters"] == ["Final", "Approved", "Accepted", "Review", "Deferred", "Bikeshedding"]


def test_matrix_ships_the_heat_ramp_as_data(hip_data: Path):
    """The frontend shades from the API's ramp, so the scale has one source."""
    matrix = hip_views.coverage_matrix(ORG, hip_data)

    assert len(matrix["ramp"]) == len(matrix["ramp_ceilings"]) + 1
    assert all(colour.startswith("#") for colour in matrix["ramp"])


def test_board_places_every_spec_and_keeps_unknown_statuses_visible(hip_data: Path):
    """Columns read as the lifecycle; an unlisted status lands in "Other"."""
    board = hip_views.governance_board(hip_data)

    placed = {column["title"]: [item["key"] for item in column["items"]] for column in board["columns"]}
    assert placed["Approved (incl. legacy Accepted)"] == [300, 150]
    assert placed["Final"] == [200]
    assert placed["In review"] == [100]
    assert placed["Retired"] == [50]
    assert placed["Other"] == [10]
    assert board["badge"] == "6 specs"


def test_views_are_absent_without_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """An org with no HIP data simply omits the views."""
    monkeypatch.setattr(hip_views.hips_spec, "MATRIX_COMPONENTS", {ORG: COMPONENTS})

    assert hip_views.coverage_matrix(ORG, tmp_path) is None
    assert hip_views.governance_board(tmp_path) is None
    assert hip_views.build_views(ORG, tmp_path) == []


def test_views_are_absent_for_an_unconfigured_org(hip_data: Path):
    """A org with no declared components has no matrix to show."""
    assert hip_views.coverage_matrix("other-org", hip_data) is None


def test_build_views_returns_board_then_matrix(hip_data: Path):
    """The board reads first: governance context before the coverage detail."""
    assert [view["id"] for view in hip_views.build_views(ORG, hip_data)] == ["hip-board", "hip-matrix"]
