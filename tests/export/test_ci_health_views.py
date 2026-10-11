"""Tests for the CI health matrix exporter."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from hiero_analytics.export.ci_health_views import ci_health_matrix

ORG = "test-org"


@pytest.fixture
def ci_health_data(tmp_path: Path) -> Path:
    """A small CI health dataset covering all relevant export states."""
    pd.DataFrame(
        [
            {
                "repo": "repo-alpha",
                "check": "actions_sha_pinned",
                "band": "actions",
                "status": "fail",
                "evidence": "unpinned workflow",
                "location": "workflow.yml:10",
            },
            {
                "repo": "repo-alpha",
                "check": "explicit_permissions",
                "band": "permissions",
                "status": "pass",
                "evidence": "permissions set",
                "location": "workflow.yml:15",
            },
            {
                "repo": "repo-alpha",
                "check": "repository_security_configuration",
                "band": "repository",
                "status": "review",
                "evidence": "needs review",
                "location": "settings.yml:4",
            },
            {
                "repo": "repo-beta",
                "check": "actions_sha_pinned",
                "band": "actions",
                "status": "review",
                "evidence": "one workflow unpinned",
                "location": "ci.yml:8",
            },
            {
                "repo": "repo-beta",
                "check": "explicit_permissions",
                "band": "permissions",
                "status": "na",
                "evidence": "no workflows",
                "location": "",
            },
            {
                "repo": "repo-beta",
                "check": "repository_security_configuration",
                "band": "repository",
                "status": "pass",
                "evidence": "repo secure",
                "location": "",
            },
            {
                "repo": "repo-gamma",
                "check": "actions_sha_pinned",
                "band": "actions",
                "status": "pass",
                "evidence": "all pinned",
                "location": "",
            },
            {
                "repo": "repo-gamma",
                "check": "explicit_permissions",
                "band": "permissions",
                "status": "pass",
                "evidence": "permissions explicit",
                "location": "",
            },
            {
                "repo": "repo-gamma",
                "check": "repository_security_configuration",
                "band": "repository",
                "status": "na",
                "evidence": "no repo configuration issue",
                "location": "",
            },
            {
                "repo": "repo-delta",
                "check": "actions_sha_pinned",
                "band": "actions",
                "status": "na",
                "evidence": "no workflows",
                "location": "",
            },
            {
                "repo": "repo-delta",
                "check": "explicit_permissions",
                "band": "permissions",
                "status": "na",
                "evidence": "no workflows",
                "location": "",
            },
            {
                "repo": "repo-delta",
                "check": "repository_security_configuration",
                "band": "repository",
                "status": "pass",
                "evidence": "repository secure",
                "location": "",
            },
        ]
    ).to_csv(tmp_path / "ci_health_checks.csv", index=False)
    return tmp_path


def test_rows_are_sorted_worst_first_and_tie_broken_by_repo_name(ci_health_data: Path):
    """Fail count takes priority, then review count, then repository name."""
    matrix = ci_health_matrix(ORG, ci_health_data)

    assert matrix is not None
    assert [row["label"] for row in matrix["rows"]] == ["repo-alpha", "repo-beta", "repo-gamma", "repo-delta"]


def test_na_rows_rank_with_pass_rows_below_fail_and_review(ci_health_data: Path):
    """na and pass do not contribute to repo severity; they fall behind fail/review rows."""
    matrix = ci_health_matrix(ORG, ci_health_data)

    assert matrix is not None
    ranking = [row["label"] for row in matrix["rows"]]
    assert ranking.index("repo-gamma") < ranking.index("repo-delta")
    assert ranking.index("repo-alpha") < ranking.index("repo-beta")


def test_matrix_adds_band_metadata_and_column_band_values(ci_health_data: Path):
    """Each column carries its declared band and the top-level header spans follow the source."""
    matrix = ci_health_matrix(ORG, ci_health_data)

    assert matrix is not None
    assert matrix["bands"] == [
        {"label": "Actions", "span": 1},
        {"label": "Permissions", "span": 1},
        {"label": "Repository", "span": 1},
    ]
    assert [column["band"] for column in matrix["columns"]] == ["actions", "permissions", "repository"]


def test_missing_or_duplicate_checks_raise_value_error(ci_health_data: Path):
    """Recognized checks must be present exactly once to build a valid matrix."""
    frame = pd.read_csv(ci_health_data / "ci_health_checks.csv")

    missing = frame[frame["check"] != "actions_sha_pinned"].copy()
    missing.to_csv(ci_health_data / "ci_health_checks.csv", index=False)
    with pytest.raises(ValueError, match="Expected exactly one actions_sha_pinned"):
        ci_health_matrix(ORG, ci_health_data)

    frame = pd.read_csv(ci_health_data / "ci_health_checks.csv")
    frame = pd.concat([frame, frame.iloc[[0]].copy()], ignore_index=True)
    frame.to_csv(ci_health_data / "ci_health_checks.csv", index=False)
    with pytest.raises(ValueError, match="Expected exactly one"):
        ci_health_matrix(ORG, ci_health_data)


def test_unknown_status_and_band_mismatch_raise_value_error(ci_health_data: Path):
    """Status validation and band validation remain strict for known checks."""
    frame = pd.read_csv(ci_health_data / "ci_health_checks.csv")
    frame.loc[0, "status"] = "pending"
    frame.to_csv(ci_health_data / "ci_health_checks.csv", index=False)
    with pytest.raises(ValueError, match="Unexpected CI health status"):
        ci_health_matrix(ORG, ci_health_data)

    frame = pd.read_csv(ci_health_data / "ci_health_checks.csv")
    frame.loc[0, "status"] = "fail"
    frame.loc[0, "band"] = "permissions"
    frame.to_csv(ci_health_data / "ci_health_checks.csv", index=False)
    with pytest.raises(ValueError, match="Unexpected CI health band"):
        ci_health_matrix(ORG, ci_health_data)


def test_missing_and_empty_csv_inputs_return_none(ci_health_data: Path, tmp_path: Path):
    """Missing or empty CSV inputs do not build a matrix."""
    assert ci_health_matrix(ORG, tmp_path) is None

    empty = pd.DataFrame(columns=["repo", "check", "band", "status", "evidence", "location"])
    empty.to_csv(ci_health_data / "ci_health_checks.csv", index=False)
    assert ci_health_matrix(ORG, ci_health_data) is None


def test_evidence_and_location_are_passthrough_and_file_only_locations_stay_valid(ci_health_data: Path):
    """The view keeps the evidence and location values exactly as exported."""
    matrix = ci_health_matrix(ORG, ci_health_data)

    assert matrix is not None
    first_row = matrix["rows"][0]
    cell = first_row["cells"][0]
    assert cell["evidence"] == "unpinned workflow"
    assert cell["location"] == "workflow.yml:10"

    row = next(row for row in matrix["rows"] if row["label"] == "repo-beta")
    permissions = next(cell for cell in row["cells"] if cell["key"] == "explicit_permissions")
    assert permissions["status"] == "na"
    assert permissions["location"] == ""
