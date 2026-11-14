"""CI health views for the Security & scorecards dashboard.

The canonical CI health artifact is long-format:
    repo, check, band, status, evidence, location, subject

This module transforms that artifact into a repository x check matrix for
interactive dashboard rendering. The long-format CSV remains the canonical
source; this view is presentation-specific.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from hiero_analytics.export.artifacts import load_csv

MATRIX_ID = "ci-health-matrix"

BAND_LABELS = {
    "actions": "Actions",
    "permissions": "Permissions",
    "repository": "Repository",
    "dependabot": "Dependabot",
}

CHECK_COLUMNS = (
    ("actions_sha_pinned", "Actions SHA Pinned", "actions"),
    ("explicit_permissions", "Explicit Permissions", "permissions"),
    ("repository_security_configuration", "Security Config", "repository"),
    ("dependabot_ecosystems", "Dependabot Ecosystems", "dependabot"),
)

# Checks that emit one row per subject (e.g. per ecosystem). Their rows collapse
# into a single matrix cell so the frontend cell contract stays unchanged.
MULTI_ROW_CHECKS = frozenset({"dependabot_ecosystems"})

# Worst status wins when several rows collapse into one cell.
STATUS_SEVERITY = {"fail": 3, "review": 2, "pass": 1, "na": 0}

CHECK_STATUSES = ("pass", "fail", "review", "na")


def _bands(columns: list[dict]) -> list[dict]:
    """Consecutive column groups as header bands in first-appearance order."""
    bands: list[dict] = []
    for column in columns:
        label = BAND_LABELS[column["band"]]
        if bands and bands[-1]["label"] == label:
            bands[-1]["span"] += 1
        else:
            bands.append({"label": label, "span": 1})
    return bands


def _repo_sort_key(row: dict) -> tuple[int, int, str]:
    """Sort by the most severe findings first, then repository name."""
    return (
        -sum(cell["status"] == "fail" for cell in row["cells"]),
        -sum(cell["status"] == "review" for cell in row["cells"]),
        row["label"],
    )


def _clean_cell_value(value: object) -> str:
    """Coerce pandas missing values to empty strings without mutating valid values."""
    if pd.isna(value):
        return ""
    return str(value)


def _collapse_rows(matches: pd.DataFrame) -> dict[str, str]:
    """Collapse several per-subject rows into one cell: worst status, joined evidence."""
    statuses = [str(status) for status in matches["status"]]

    for status in statuses:
        if status not in STATUS_SEVERITY:
            raise ValueError(f"Unexpected CI health status {status!r}")

    subjects = (
        [_clean_cell_value(value) for value in matches["subject"]] if "subject" in matches else [""] * len(matches)
    )
    evidence = [_clean_cell_value(value) for value in matches["evidence"]]
    locations = [_clean_cell_value(value) for value in matches["location"]]

    lines = [f"{subject}: {text}" if subject else text for subject, text in zip(subjects, evidence, strict=True)]

    return {
        "status": max(statuses, key=STATUS_SEVERITY.__getitem__),
        "band": str(matches.iloc[0]["band"]),
        "evidence": "\n".join(lines),
        "location": "; ".join(dict.fromkeys(location for location in locations if location)),
    }


def ci_health_matrix(_org: str, org_data_dir: Path) -> dict | None:
    """Build the CI health repository x check matrix."""
    try:
        frame = load_csv(org_data_dir / "ci_health_checks.csv")
    except pd.errors.EmptyDataError:
        return None

    if frame.empty:
        return None

    if "band" not in frame.columns:
        raise ValueError("CI health CSV is missing the 'band' column")

    rows = []

    for repo, repo_frame in frame.groupby("repo", sort=True):
        cells = []

        for check_key, label, band in CHECK_COLUMNS:
            matches = repo_frame[repo_frame["check"] == check_key]

            if check_key in MULTI_ROW_CHECKS:
                if matches.empty:
                    raise ValueError(f"Expected at least one {check_key} result for {repo}, found 0")
                result = _collapse_rows(matches)
            else:
                if len(matches) != 1:
                    raise ValueError(f"Expected exactly one {check_key} result for {repo}, found {len(matches)}")
                result = matches.iloc[0]

            band_value = str(result["band"])
            status = str(result["status"])

            if band_value != band:
                raise ValueError(f"Unexpected CI health band {band_value!r} for {repo}/{check_key}; expected {band!r}")

            if status not in CHECK_STATUSES:
                raise ValueError(f"Unexpected CI health status {status!r} for {repo}/{check_key}")

            cells.append(
                {
                    "key": check_key,
                    "label": label,
                    "status": status,
                    "evidence": _clean_cell_value(result["evidence"]),
                    "location": _clean_cell_value(result["location"]),
                }
            )

        rows.append(
            {
                "key": str(repo),
                "label": str(repo),
                "cells": cells,
            }
        )

    rows.sort(key=_repo_sort_key)

    columns = [{"key": key, "label": label, "band": band} for key, label, band in CHECK_COLUMNS]

    return {
        "id": MATRIX_ID,
        "kind": "ci_health_matrix",
        "group": "CI health",
        "title": "CI health matrix",
        "description": (
            "Repository-level CI health checks sorted worst-first by fail count, then review count, "
            "then repository name. Pass and na do not affect repo priority. Click a fail or review cell "
            "to inspect the supporting evidence."
        ),
        "badge": f"{len(rows)} repositories",
        "source": "ci_health_checks.csv",
        "row_header": "Repository",
        "columns": columns,
        "bands": _bands(columns),
        "rows": rows,
        "filters": list(CHECK_STATUSES),
    }


def build_views(org: str, org_data_dir: Path) -> list[dict]:
    """Build the CI health dashboard views for an organization."""
    matrix = ci_health_matrix(org, org_data_dir)

    if matrix is None:
        return []

    return [matrix]
