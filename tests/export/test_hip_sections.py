"""Tests for the HIPs family's prebuilt dashboard sections (board + matrix)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from hiero_analytics.export.hip_sections import _board_section, _matrix_section

ORG = "hiero-ledger"


def _write(tmp_path: Path, name: str, df: pd.DataFrame) -> None:
    df.to_csv(tmp_path / name, index=False)


def _base_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    activity = pd.DataFrame(
        [
            {"hip": 551, "repo": f"{ORG}/hiero-consensus-node", "merged_prs": 6, "open_prs": 0},
            {"hip": 551, "repo": f"{ORG}/hiero-sdk-java", "merged_prs": 2, "open_prs": 0},
            {"hip": 551, "repo": f"{ORG}/hiero-sdk-go", "merged_prs": 1, "open_prs": 1},
            # Open-only cell: renders the open marker, still counts as a gap.
            {"hip": 551, "repo": f"{ORG}/hiero-sdk-js", "merged_prs": 0, "open_prs": 2},
            {"hip": 904, "repo": f"{ORG}/hiero-sdk-java", "merged_prs": 1, "open_prs": 0},
        ]
    )
    summary = pd.DataFrame(
        [
            {"hip": 551, "hip_title": "Batch transactions", "hip_status": "Final", "hip_created": "2022-07-25"},
            {"hip": 904, "hip_title": "Frictionless Airdrops", "hip_status": "Approved", "hip_created": "2024-02-25"},
            # No activity anywhere: still a matrix row (all dashes).
            {
                "hip": 173,
                "hip_title": "Opt-in merged scheduling",
                "hip_status": "Deferred",
                "hip_created": "2021-10-18",
            },
        ]
    )
    return activity, summary


def test_matrix_renders_every_spec_hottest_first(tmp_path: Path):
    """All inventory specs appear, most referencing activity first."""
    activity, summary = _base_frames()
    _write(tmp_path, "hip_repo_activity.csv", activity)
    _write(tmp_path, "hip_summary.csv", summary)

    section = _matrix_section(ORG, tmp_path)

    assert section is not None
    assert section["badge"] == "3 HIPs"
    html = section["html"]
    # Hottest first (551 has 12 referencing PRs, 904 has 1), blanks last.
    assert html.index("HIP-551") < html.index("HIP-904") < html.index("HIP-173")
    # The governance column explains blank rows.
    assert "Governance" in html
    assert "Deferred" in html
    # Cell states: counts, the open-only marker, and the gap list.
    assert "2 merged PRs" in html
    assert "open PRs, none merged" in html
    assert "js · cpp · rust · swift · python" in html
    # A fully blank spec says so plainly — it does not single out the SDKs.
    assert "no activity found" in html
    assert "no SDK activity found" not in html
    # The matrix is filterable by text and by governance status.
    assert "hipMxFilter" in html
    assert "hipMxStatus" in html and 'data-s="Deferred"' in html.replace("'", '"')


def test_gap_column_distinguishes_service_only_activity(tmp_path: Path):
    """Service-only activity earns the SDK-specific note; blank rows the plain one."""
    activity = pd.DataFrame([{"hip": 904, "repo": f"{ORG}/hiero-consensus-node", "merged_prs": 3, "open_prs": 0}])
    summary = pd.DataFrame(
        [{"hip": 904, "hip_title": "Frictionless Airdrops", "hip_status": "Final", "hip_created": "2024-02-25"}]
    )
    _write(tmp_path, "hip_repo_activity.csv", activity)
    _write(tmp_path, "hip_summary.csv", summary)

    section = _matrix_section(ORG, tmp_path)

    assert section is not None
    assert "no SDK activity found" in section["html"]


def test_matrix_gap_list_confirms_full_coverage(tmp_path: Path):
    """A spec with merged PRs in every SDK earns the all-SDKs check."""
    _activity, summary = _base_frames()
    sdks = ("java", "go", "js", "cpp", "rust", "swift", "python")
    activity = pd.DataFrame(
        [{"hip": 904, "repo": f"{ORG}/hiero-sdk-{sdk}", "merged_prs": 1, "open_prs": 0} for sdk in sdks]
    )
    _write(tmp_path, "hip_repo_activity.csv", activity)
    _write(tmp_path, "hip_summary.csv", summary[summary["hip"] == 904])

    section = _matrix_section(ORG, tmp_path)

    assert section is not None
    assert "all SDKs" in section["html"]


@pytest.mark.parametrize("missing", ["hip_repo_activity.csv", "hip_summary.csv"])
def test_matrix_section_needs_both_csvs(tmp_path: Path, missing: str):
    """Absent inputs (e.g. an offline run that skipped) yield no section."""
    activity, summary = _base_frames()
    files = {"hip_repo_activity.csv": activity, "hip_summary.csv": summary}
    for name, frame in files.items():
        if name != missing:
            _write(tmp_path, name, frame)

    assert _matrix_section(ORG, tmp_path) is None


def test_matrix_section_unknown_org(tmp_path: Path):
    """Orgs without a declared component set get no matrix."""
    activity, summary = _base_frames()
    _write(tmp_path, "hip_repo_activity.csv", activity)
    _write(tmp_path, "hip_summary.csv", summary)

    assert _matrix_section("some-other-org", tmp_path) is None


def test_board_section_chips_and_detail_bar(tmp_path: Path):
    """The governance board renders columns, pickable chips, and the info bar."""
    summary = pd.DataFrame(
        [
            {"hip": 1448, "hip_title": "Simple Event Broadcast", "hip_status": "Approved", "hip_created": "2025-10-01"},
            {"hip": 551, "hip_title": "Batch transactions", "hip_status": "Final", "hip_created": "2022-07-25"},
            {
                "hip": 173,
                "hip_title": "Opt-in merged scheduling",
                "hip_status": "Deferred",
                "hip_created": "2021-10-18",
            },
        ]
    )
    summary.to_csv(tmp_path / "hip_summary.csv", index=False)

    section = _board_section(tmp_path)

    assert section is not None
    html = section["html"]
    assert "Approved (incl. legacy Accepted)" in html and "Retired" in html
    assert 'data-t="Simple Event Broadcast"' in html
    assert "hipBoardPick(this,1448)" in html
    assert "hip-board-info" in html
    assert section["download"]["name"] == "hip_governance_board.csv"
