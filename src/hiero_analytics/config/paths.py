"""Defines configuration constants for paths and directories used in the analytics module."""

from __future__ import annotations

import os
from pathlib import Path

from hiero_analytics.config.orgs import ORGS as KNOWN_ORGS
from hiero_analytics.config.orgs import extra_orgs

# Import-time *defaults* only — runners that support multiple orgs must accept an
# explicit org argument (see run_contributor_activity_org.main) rather than lean
# on these, so one process can serve several orgs without env mutation.
ORG = os.getenv("GITHUB_ORG", "hiero-ledger")
REPO = os.getenv("GITHUB_REPO", "hiero-sdk-python")

# Registry in display order — primary org first. Just an ordering view of
# config.orgs, not a copy: everything org-shaped is read from there.
ORGS = (*(p for p in KNOWN_ORGS if p.name == ORG), *(p for p in KNOWN_ORGS if p.name != ORG))

# Orgs the full run also renders, derived from the registry (filtered by
# GITHUB_EXTRA_ORGS when set) so the orchestrator and heatmap share one source.
# Re-exported here since consumers import orgs from ``paths``.
EXTRA_ORGS = extra_orgs()

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC = PROJECT_ROOT / "src" / "hiero_analytics"

OUTPUTS_DIR = PROJECT_ROOT / "outputs"

# Local-only directory for raw/manual input data (Discord exports, etc.).
# Gitignored — never commit the contents.
INPUTS_DIR = PROJECT_ROOT / "inputs"

DATA_DIR = OUTPUTS_DIR / "data"

REPO_DATA_DIR = DATA_DIR / "repo"
ORG_DATA_DIR = DATA_DIR / "org"

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


def ensure_org_dirs(org: str) -> Path:
    """Create and return the org's data output directory (``outputs/data/org/<org>``)."""
    org_data_dir = ORG_DATA_DIR / org.replace("/", "_")
    org_data_dir.mkdir(parents=True, exist_ok=True)
    return org_data_dir


def ensure_repo_dirs(repo: str) -> Path:
    """Create and return the repo's data output directory (``outputs/data/repo/<owner_repo>``)."""
    repo_data_dir = REPO_DATA_DIR / repo.replace("/", "_")
    repo_data_dir.mkdir(parents=True, exist_ok=True)
    return repo_data_dir
