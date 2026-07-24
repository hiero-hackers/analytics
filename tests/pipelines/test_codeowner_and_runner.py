"""Integration tests for the codeowner and runner analytics pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import matplotlib
import pytest

matplotlib.use("Agg")

import hiero_analytics.pipelines.codeowner_and_runner as runner
from hiero_analytics.data_sources.models import (
    CodeOwnersRecord,
    RepositoryRecord,
    RunnerRecord,
)


@pytest.fixture
def mock_github_client():
    """Mock GitHubClient."""
    return MagicMock()


@pytest.fixture
def synthetic_repos():
    """Synthetic repository data."""
    return [
        RepositoryRecord(
            full_name="hiero-ledger/repo1",
            name="repo1",
            owner="hiero-ledger",
        ),
        RepositoryRecord(
            full_name="hiero-ledger/repo2",
            name="repo2",
            owner="hiero-ledger",
        ),
    ]


@pytest.fixture
def synthetic_codeowners():
    """Synthetic CODEOWNERS data."""
    return [
        CodeOwnersRecord(repo="repo1", status=True),
        CodeOwnersRecord(repo="repo2", status=False),
    ]


@pytest.fixture
def synthetic_runners():
    """Synthetic runner data."""
    return [
        RunnerRecord(
            repo="repo1",
            workflow_file="ci.yml",
            job_name="test-job-1",
            runner="self-hosted",
            is_self_hosted=True,
        ),
        RunnerRecord(
            repo="repo2",
            workflow_file="ci.yml",
            job_name="test-job-2",
            runner="ubuntu-latest",
            is_self_hosted=False,
        ),
    ]


def test_main_creates_output_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_github_client,
    synthetic_repos,
    synthetic_codeowners,
    synthetic_runners,
):
    """Running main() should create expected chart and data files."""
    # Redirect paths to tmp_path and stub the GitHub client
    monkeypatch.setattr(
        "hiero_analytics.pipelines.codeowner_and_runner.org_context",
        lambda _org: (mock_github_client, tmp_path / "data", tmp_path / "charts"),
    )

    # Mock fetch functions
    monkeypatch.setattr(
        "hiero_analytics.pipelines.codeowner_and_runner.fetch_org_repos",
        lambda _client, _org: synthetic_repos,
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.codeowner_and_runner.get_codeowners_for_repos",
        lambda _client, _org, _repos: synthetic_codeowners,
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.codeowner_and_runner.get_workflow_for_repos",
        lambda _client, _org, _repos: synthetic_runners,
    )

    # Run the main function
    runner.main()

    # Assert expected output files exist
    charts_dir = tmp_path / "charts"
    data_dir = tmp_path / "data"

    expected_charts = [
        "org_codeowner_summary.png",
        "org_codeowner_by_repo.png",
        "org_runner_chart.png",
    ]
    expected_data = [
        "repo_wise_codeowner_status.csv",
        "org_runner_status.csv",
        "codeowners_report.md",
        "runner_report.md",
    ]

    for chart_file in expected_charts:
        chart_path = charts_dir / chart_file
        assert chart_path.exists(), f"Chart {chart_file} not created"
        assert os.path.getsize(chart_path) > 0, f"Chart {chart_file} is empty"

    for data_file in expected_data:
        data_path = data_dir / data_file
        assert data_path.exists(), f"Data file {data_file} not created"
        assert os.path.getsize(data_path) > 0, f"Data file {data_file} is empty"


# ---------------------------------------------------------
# fetch helpers: cache-hit short-circuit vs fresh scan
# ---------------------------------------------------------


def test_get_codeowners_returns_cache_without_scanning(monkeypatch, mock_github_client, synthetic_repos):
    """A warm cache is returned as-is, without touching the GitHub API."""
    cached = [CodeOwnersRecord(repo="repo1", status=True)]
    monkeypatch.setattr(runner, "load_records_cache", lambda **_kw: cached)

    def _boom(*_a, **_k):
        raise AssertionError("has_codeowners_file must not be called on a cache hit")

    monkeypatch.setattr(runner, "has_codeowners_file", _boom)

    assert runner.get_codeowners_for_repos(mock_github_client, "org", synthetic_repos) is cached


def test_get_codeowners_scans_and_persists_on_cache_miss(monkeypatch, mock_github_client, synthetic_repos):
    """A cold cache triggers a fresh scan and writes the result back."""
    monkeypatch.setattr(runner, "load_records_cache", lambda **_kw: None)
    monkeypatch.setattr(runner, "has_codeowners_file", lambda _c, _o, name: name == "repo1")
    saved: dict = {}
    monkeypatch.setattr(runner, "save_records_cache", lambda **kw: saved.update(kw))

    records = runner.get_codeowners_for_repos(mock_github_client, "org", synthetic_repos)

    assert {r.repo: r.status for r in records} == {"repo1": True, "repo2": False}
    assert saved["records"] == records  # persisted for next time


def test_get_workflow_returns_cache_without_scanning(monkeypatch, mock_github_client, synthetic_repos):
    """A warm runner cache short-circuits the per-repo workflow scan."""
    cached = [RunnerRecord(repo="repo1", workflow_file="ci.yml", job_name="j", runner="x", is_self_hosted=None)]
    monkeypatch.setattr(runner, "load_records_cache", lambda *_a, **_k: cached)

    def _boom(*_a, **_k):
        raise AssertionError("fetch_repo_workflows must not run on a cache hit")

    monkeypatch.setattr(runner, "fetch_repo_workflows", _boom)

    assert runner.get_workflow_for_repos(mock_github_client, "org", synthetic_repos) is cached
