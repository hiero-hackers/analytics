"""CI health views for the Security & scorecards dashboard.

The canonical CI health artifact is long-format:
    repo, check, band, status, evidence, location

This module transforms that artifact into a repository x check matrix for
interactive dashboard rendering. The long-format CSV remains the canonical
source; this view is presentation-specific.
"""

from __future__ import annotations

from pathlib import Path

from hiero_analytics.export.artifacts import load_csv

MATRIX_ID = "ci-health-matrix"

CHECK_COLUMNS = (
    ("actions_sha_pinned", "Actions SHA Pinned"),
    ("explicit_permissions", "Explicit Permissions"),
    ("repository_security_configuration", "Security Config"),
)

CHECK_STATUSES = ("pass", "fail", "review", "na")


def ci_health_matrix(_org: str, org_data_dir: Path) -> dict | None:
    """Build the CI health repository x check matrix."""
    frame = load_csv(org_data_dir / "ci_health_checks.csv")

    if frame.empty:
        return None

    rows = []

    for repo, repo_frame in frame.groupby("repo", sort=True):
        cells = []

        for check_key, label in CHECK_COLUMNS:
            matches = repo_frame[repo_frame["check"] == check_key]

            if len(matches) != 1:
                raise ValueError(f"Expected exactly one {check_key} result for {repo}, found {len(matches)}")

            result = matches.iloc[0]
            status = str(result["status"])

            if status not in CHECK_STATUSES:
                raise ValueError(f"Unexpected CI health status {status!r} for {repo}/{check_key}")

            cells.append(
                {
                    "key": check_key,
                    "label": label,
                    "status": status,
                    "evidence": str(result["evidence"]),
                    "location": str(result["location"]),
                }
            )

        rows.append(
            {
                "key": str(repo),
                "label": str(repo),
                "cells": cells,
            }
        )

    return {
        "id": MATRIX_ID,
        "kind": "ci_health_matrix",
        "group": "CI health",
        "title": "CI health matrix",
        "description": (
            "Repository-level CI health checks covering GitHub Actions SHA pinning, "
            "explicit workflow permissions, and repository security configuration. "
            "Click a fail or review cell to inspect the supporting evidence."
        ),
        "badge": f"{len(rows)} repositories",
        "source": "ci_health_checks.csv",
        "row_header": "Repository",
        "columns": [{"key": key, "label": label} for key, label in CHECK_COLUMNS],
        "rows": rows,
        "filters": list(CHECK_STATUSES),
    }


def build_views(org: str, org_data_dir: Path) -> list[dict]:
    """Build the CI health dashboard views for an organization."""
    matrix = ci_health_matrix(org, org_data_dir)

    if matrix is None:
        return []

    return [matrix]
