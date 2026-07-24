"""Defines configuration constants for paths and directories used in the analytics module."""

from __future__ import annotations

import os
from pathlib import Path

# Import-time *defaults* only — runners that support multiple orgs must accept an
# explicit org argument (see run_contributor_activity_org.main) rather than lean
# on these, so one process can serve several orgs without env mutation.
ORG = os.getenv("GITHUB_ORG", "hiero-ledger")
REPO = os.getenv("GITHUB_REPO", "hiero-sdk-python")

# Secondary orgs the multi-org pipelines also render (comma-separated) — the
# single "extra orgs" concept shared by run_all's contributor pass and the
# contributor heatmap. The default keeps the composition org on every dashboard
# build; set GITHUB_EXTRA_ORGS="" to disable extras entirely.
EXTRA_ORGS = [org.strip() for org in os.getenv("GITHUB_EXTRA_ORGS", "hiero-hackers").split(",") if org.strip()]

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC = PROJECT_ROOT / "src" / "hiero_analytics"

OUTPUTS_DIR = PROJECT_ROOT / "outputs"

# Local-only directory for raw/manual input data (Discord exports, etc.).
# Gitignored — never commit the contents.
INPUTS_DIR = PROJECT_ROOT / "inputs"

DATA_DIR = OUTPUTS_DIR / "data"
CHARTS_DIR = OUTPUTS_DIR / "charts"

REPO_DATA_DIR = DATA_DIR / "repo"
ORG_DATA_DIR = DATA_DIR / "org"

REPO_CHARTS_DIR = CHARTS_DIR / "repo"
ORG_CHARTS_DIR = CHARTS_DIR / "org"

# Persistent "system of record" datasets for incremental fetching (see
# data_sources/dataset_store.py). Gitignored locally; CI persists them across
# runs via the GitHub Actions cache, unlike the short-lived TTL cache.
DATASETS_DIR = DATA_DIR / "datasets"


def dataset_path(resource: str, scope: str, fingerprint: str = "all") -> Path:
    """Path to a persistent incremental-fetch dataset file.

    e.g. ``dataset_path("issues", "hiero-ledger")`` ->
    ``outputs/data/datasets/issues_hiero-ledger_all.json``.
    """
    scope_slug = scope.replace("/", "_")
    return DATASETS_DIR / f"{resource}_{scope_slug}_{fingerprint}.json"


def ensure_output_dirs() -> None:
    """
    Ensure the above directories exist.

    Should be called by runner scripts before writing files to ensure they can be
    saved to that location.
    """
    for path in [
        OUTPUTS_DIR,
        DATA_DIR,
        CHARTS_DIR,
        REPO_DATA_DIR,
        ORG_DATA_DIR,
        REPO_CHARTS_DIR,
        ORG_CHARTS_DIR,
        DATASETS_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def ensure_org_dirs(org: str) -> tuple[Path, Path]:
    """
    Create org-specific output directories.

    Args:
        org: Organization identifier, such as a GitHub organization name or slug.

    Returns:
        A tuple containing:
            org_data_dir: Directory for organization-level data outputs.
            org_charts_dir: Directory for organization-level chart outputs.
    """
    org_name = org.replace("/", "_")

    org_data_dir = ORG_DATA_DIR / org_name
    org_charts_dir = ORG_CHARTS_DIR / org_name

    org_data_dir.mkdir(parents=True, exist_ok=True)
    org_charts_dir.mkdir(parents=True, exist_ok=True)

    return org_data_dir, org_charts_dir


def ensure_repo_dirs(repo: str) -> tuple[Path, Path]:
    """
    Create repo-specific output directories.

    Returns:
        repo_data_dir, repo_charts_dir
    """
    repo_name = repo.replace("/", "_")

    repo_data_dir = REPO_DATA_DIR / repo_name
    repo_charts_dir = REPO_CHARTS_DIR / repo_name

    repo_data_dir.mkdir(parents=True, exist_ok=True)
    repo_charts_dir.mkdir(parents=True, exist_ok=True)

    return repo_data_dir, repo_charts_dir
