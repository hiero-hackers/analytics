"""Tests for the onboarding-pipeline DataFrame builders."""

from __future__ import annotations

import pandas as pd

from hiero_analytics.analysis.onboarding_pipeline import (
    build_gfi_pipeline,
    build_onboarding_repo_pipeline,
)

# -- build_gfi_pipeline -------------------------------------------------------


def test_build_gfi_pipeline_merges_and_sorts_by_year():
    """Overlapping years combine into one row; output is sorted by year."""
    gfi = pd.DataFrame({"year": [2023, 2022], "count": [5, 3]})
    gfic = pd.DataFrame({"year": [2022, 2023], "count": [8, 6]})

    result = build_gfi_pipeline(gfi, gfic)

    assert list(result["year"]) == [2022, 2023]
    assert list(result["gfi"]) == [3, 5]
    assert list(result["gfic"]) == [8, 6]


def test_build_gfi_pipeline_fills_missing_years_with_zero_ints():
    """A year present in only one frame fills the other side with int 0."""
    gfi = pd.DataFrame({"year": [2021], "count": [4]})
    gfic = pd.DataFrame({"year": [2022], "count": [9]})

    result = build_gfi_pipeline(gfi, gfic)

    assert list(result["year"]) == [2021, 2022]
    assert list(result["gfi"]) == [4, 0]
    assert list(result["gfic"]) == [0, 9]
    # Counts must stay integers, not become 0.0 floats after the outer merge.
    assert result["gfi"].dtype == int
    assert result["gfic"].dtype == int


# -- build_onboarding_repo_pipeline -------------------------------------------


def test_build_onboarding_repo_pipeline_sorts_by_gfi_desc():
    """Repositories are ordered by GFI count, highest first."""
    gfi = pd.DataFrame({"repo": ["a", "b", "c"], "count": [1, 9, 4]})
    gfic = pd.DataFrame({"repo": ["a", "b", "c"], "count": [2, 2, 2]})

    result = build_onboarding_repo_pipeline(gfi, gfic)

    assert list(result["repo"]) == ["b", "c", "a"]
    assert list(result["gfi"]) == [9, 4, 1]


def test_build_onboarding_repo_pipeline_fills_missing_repos_with_zero_ints():
    """A repo present in only one frame fills the other side with int 0.

    Regression: the outer merge + ``fillna(0)`` would otherwise leave the
    count columns as floats (e.g. ``5.0``), which then render as ``5.0`` in
    every downstream chart/table.
    """
    gfi = pd.DataFrame({"repo": ["only-gfi"], "count": [5]})
    gfic = pd.DataFrame({"repo": ["only-gfic"], "count": [7]})

    result = build_onboarding_repo_pipeline(gfi, gfic)

    by_repo = result.set_index("repo")
    assert by_repo.loc["only-gfi", "gfi"] == 5
    assert by_repo.loc["only-gfi", "gfic"] == 0
    assert by_repo.loc["only-gfic", "gfi"] == 0
    assert by_repo.loc["only-gfic", "gfic"] == 7
    assert result["gfi"].dtype == int
    assert result["gfic"].dtype == int
