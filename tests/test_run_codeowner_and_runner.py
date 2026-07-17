"""Integration tests for the codeowner and runner analytics pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import matplotlib
import pytest

matplotlib.use("Agg")

import hiero_analytics.run_codeowner_and_runner as runner
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
    # Redirect paths to tmp_path
    monkeypatch.setattr(
        "hiero_analytics.run_codeowner_and_runner.ensure_org_dirs",
        lambda _org: (tmp_path / "data", tmp_path / "charts"),
    )

    # Mock fetch functions
    monkeypatch.setattr(
        "hiero_analytics.run_codeowner_and_runner.fetch_org_repos",
        lambda _client, _org: synthetic_repos,
    )
    monkeypatch.setattr(
        "hiero_analytics.run_codeowner_and_runner.get_codeowners_for_repos",
        lambda _client, _org, _repos: synthetic_codeowners,
    )
    monkeypatch.setattr(
        "hiero_analytics.run_codeowner_and_runner.get_workflow_for_repos",
        lambda _client, _org, _repos: synthetic_runners,
    )

    # Mock GitHubClient initialization
    monkeypatch.setattr(
        "hiero_analytics.run_codeowner_and_runner.GitHubClient",
        lambda: mock_github_client,
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
