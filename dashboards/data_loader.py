"""Helpers for loading dashboard-ready datasets.

Primary source is generated CSV outputs under:
    outputs/data/
or:
    outputs/data/org/<org>/

If CSV outputs are unavailable, this module fetches live GitHub API data and
derives equivalent dashboard frames.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

import pandas as pd
from hiero_analytics.analysis.dataframe_utils import (
    count_by,
    filter_by_labels,
    issues_to_dataframe,
    )
from hiero_analytics.analysis.onboarding_pipeline import (
    build_gfi_pipeline,
    build_onboarding_repo_pipeline,
    )
from hiero_analytics.config.paths import ORG, REPO
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import (
    fetch_org_issues_graphql,
    fetch_repo_issues_graphql,
    )
from hiero_analytics.domain.labels import (
    DIFFICULTY_LEVELS,
    GOOD_FIRST_ISSUE,
    GOOD_FIRST_ISSUE_CANDIDATE,
    UNKNOWN_DIFFICULTY,
    )

DASHBOARDS_DIR = Path(__file__).resolve().parent
REPO_ROOT = DASHBOARDS_DIR.parent
ANALYTICS_OUTPUTS_DATA = REPO_ROOT / "outputs" / "data"
ORG_SCOPED_DATA = ANALYTICS_OUTPUTS_DATA / "org"


DATA_FILES = {
    "gfi_pipeline": "gfi_pipeline.csv",
    "gfi_total_by_repo": "gfi_total_by_repo.csv",
    "gfi_yearly": "gfi_yearly.csv",
    "gfic_yearly": "gfic_yearly.csv",
    "onboarding_repo_pipeline": "onboarding_repo_pipeline.csv",
    "difficulty_distribution": "difficulty_distribution_30_days.csv",
    "difficulty_by_repo": "difficulty_by_repo_30_days.csv",
}


def _first_org_data_dir() -> Path | None:
    """Return the first org-scoped data directory if available."""
    if not ORG_SCOPED_DATA.exists():
        return None

    org_dirs = sorted([p for p in ORG_SCOPED_DATA.iterdir() if p.is_dir()])
    if not org_dirs:
        return None

    return org_dirs[0]


def resolve_data_dir() -> Path:
    """Resolve the preferred data directory for dashboard CSV files."""
    org_dir = _first_org_data_dir()
    if org_dir is not None:
        return org_dir
    return ANALYTICS_OUTPUTS_DATA


def _read_csv_if_exists(path: Path) -> pd.DataFrame:
    """Return CSV content or an empty frame if the file is missing."""
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def has_dashboard_outputs() -> bool:
    """Return whether at least one expected dashboard CSV exists."""
    data_dir = resolve_data_dir()
    return any((data_dir / filename).exists() for filename in DATA_FILES.values())


def _add_src_to_path() -> None:
    """Ensure local package imports work when running streamlit from repo root."""
    src_path = REPO_ROOT / "src"
    src_str = str(src_path)
    if src_str not in sys.path:
        sys.path.insert(0, src_str)


def _empty_dashboard_data() -> dict[str, pd.DataFrame]:
    """Return an empty dashboard payload matching expected keys."""
    return {key: pd.DataFrame() for key in DATA_FILES}


def _assign_difficulty(labels: list[str], specs: tuple[object, ...], unknown: str) -> str:
    label_set = set(labels or [])
    for spec in specs:
        if spec.matches(label_set):
            return spec.name
    return unknown


def _load_live_api_fallback(
    *,
    scope: Literal["repo", "org"] = "repo",
    ) -> dict[str, pd.DataFrame]:
    """Build dashboard datasets from live GitHub API data.

    Uses configured ORG/REPO. Scope controls whether fallback fetches data
    from only one repository (fast) or the full organization (broader).
    """
    try:
        _add_src_to_path()
    except Exception:
        return _empty_dashboard_data()

    try:
        client = GitHubClient()
        if scope == "org":
            issues = fetch_org_issues_graphql(
                client,
                org=ORG,
                states=["OPEN", "CLOSED"],
                max_workers=3,
            )
        else:
            issues = fetch_repo_issues_graphql(
                client,
                owner=ORG,
                repo=REPO,
                states=["OPEN", "CLOSED"],
            )
    except Exception:
        return _empty_dashboard_data()

    df = issues_to_dataframe(issues)
    if df.empty:
        return _empty_dashboard_data()

    gfi_df = filter_by_labels(df, GOOD_FIRST_ISSUE.labels)
    gfic_df = filter_by_labels(df, GOOD_FIRST_ISSUE_CANDIDATE.labels)

    gfi_yearly = count_by(gfi_df, "year")
    gfic_yearly = count_by(gfic_df, "year")
    gfi_total_by_repo = count_by(gfi_df, "repo")
    gfic_total_by_repo = count_by(gfic_df, "repo")

    pipeline = build_gfi_pipeline(gfi_yearly, gfic_yearly)
    onboarding = build_onboarding_repo_pipeline(gfi_total_by_repo, gfic_total_by_repo)

    diff_df = df.copy()
    diff_df["difficulty"] = diff_df["labels"].apply(
        lambda labels: _assign_difficulty(labels, DIFFICULTY_LEVELS, UNKNOWN_DIFFICULTY)
    )

    difficulty_distribution = (
        diff_df.groupby("difficulty", as_index=False)
        .size()
        .rename(columns={"size": "count"})
    )

    difficulty_cols = [UNKNOWN_DIFFICULTY, *[spec.name for spec in DIFFICULTY_LEVELS]]
    difficulty_by_repo = (
        diff_df.groupby(["repo", "difficulty"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=difficulty_cols, fill_value=0)
        .reset_index()
    )

    return {
        "gfi_pipeline": pipeline,
        "gfi_total_by_repo": gfi_total_by_repo,
        "gfi_yearly": gfi_yearly,
        "gfic_yearly": gfic_yearly,
        "onboarding_repo_pipeline": onboarding,
        "difficulty_distribution": difficulty_distribution,
        "difficulty_by_repo": difficulty_by_repo,
    }


def load_dashboard_data(
    *,
    fallback_scope: Literal["repo", "org"] = "repo",
    ) -> dict[str, pd.DataFrame]:
    """Load all dashboard CSVs from resolved output directory.

    Returns a mapping keyed by logical dataset name from DATA_FILES.
    Missing files are represented by empty DataFrames. If no expected output
    files exist at all, a live API fallback is attempted.
    """
    if not has_dashboard_outputs():
        return _load_live_api_fallback(scope=fallback_scope)

    data_dir = resolve_data_dir()
    loaded: dict[str, pd.DataFrame] = {}

    for key, filename in DATA_FILES.items():
        loaded[key] = _read_csv_if_exists(data_dir / filename)

    return loaded