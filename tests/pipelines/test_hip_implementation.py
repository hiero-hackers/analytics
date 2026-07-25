"""Integration tests for the HIP-implementation pipeline runner."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

import hiero_analytics.pipelines.hip_implementation as runner
from hiero_analytics.data_sources.models import HipReferenceRecord, HipSpecRecord

ORG = "test-org"

EXPECTED_CSVS = [
    "hip_pr_evidence.csv",
    "hip_unknown_references.csv",
    "hip_repo_activity.csv",
    "hip_repo_engagement.csv",
    "hip_summary.csv",
]


def _patch_pipeline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, inventory, references) -> None:
    """Redirect pipeline inputs and output directories to tmp_path."""
    monkeypatch.setattr(
        "hiero_analytics.pipelines.hip_implementation.org_context",
        lambda _org: (MagicMock(), tmp_path / "data", tmp_path / "charts"),
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.hip_implementation.fetch_hip_inventory",
        lambda _client, **_k: inventory,
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.hip_implementation.fetch_org_pr_hip_refs_graphql",
        lambda _client, _org, **_k: references,
    )


def _spec(number: int, status: str = "Final") -> HipSpecRecord:
    return HipSpecRecord(
        number=number,
        title=f"Spec {number}",
        status=status,
        category="Service",
        hip_type="Standards Track",
        created="2024-01-01",
        updated="",
        updated_at=datetime(2024, 1, 1, tzinfo=UTC),
    )


def _ref(pr_number: int, hip: int | None) -> HipReferenceRecord:
    return HipReferenceRecord(
        repo=f"{ORG}/sdk",
        pr_number=pr_number,
        pr_title=f"PR {pr_number}",
        pr_state="MERGED",
        pr_created_at=datetime(2026, 1, 1, tzinfo=UTC),
        pr_merged_at=datetime(2026, 1, 15, tzinfo=UTC),
        hip=hip,
        match_sources="title" if hip is not None else "",
        snippet=f"HIP-{hip}" if hip is not None else "",
        author="alice",
        updated_at=datetime(2026, 1, 16, tzinfo=UTC),
    )


def test_main_writes_all_evidence_tables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Running main() writes every evidence CSV with validated content."""
    _patch_pipeline(monkeypatch, tmp_path, [_spec(551), _spec(173, status="Accepted")], [_ref(1, 551), _ref(2, None)])

    runner.main(ORG)

    for csv_name in EXPECTED_CSVS:
        path = tmp_path / "data" / csv_name
        assert path.exists(), f"{csv_name} not created"

    evidence = pd.read_csv(tmp_path / "data" / "hip_pr_evidence.csv")
    assert list(evidence["hip"]) == [551]
    assert evidence.iloc[0]["url"] == f"https://github.com/{ORG}/sdk/pull/1"

    summary = pd.read_csv(tmp_path / "data" / "hip_summary.csv").set_index("hip")
    assert summary.loc[551, "evidence_class"] == "merged"
    assert summary.loc[173, "evidence_class"] == "none"


def test_main_handles_empty_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """No specs and no references still writes (empty) tables without crashing."""
    _patch_pipeline(monkeypatch, tmp_path, [], [])

    runner.main(ORG)

    for csv_name in EXPECTED_CSVS:
        assert (tmp_path / "data" / csv_name).exists(), f"{csv_name} not created"
