"""Integration tests for the maintainer pipeline analytics runner."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import matplotlib
import pytest

matplotlib.use("Agg")

import hiero_analytics.pipelines.maintainer_pipeline as runner
from hiero_analytics.data_sources.models import ContributorActivityRecord

# Test data factories


def _test_activity(
    repo: str,
    activity_type: str,
    actor: str,
    days_ago: int,
) -> ContributorActivityRecord:
    """Create a contributor activity record that occurred ``days_ago`` days ago."""
    return ContributorActivityRecord(
        repo=repo,
        activity_type=activity_type,
        actor=actor,
        occurred_at=datetime.now(UTC) - timedelta(days=days_ago),
        target_type="pull_request",
        target_number=1,
    )


# Fixtures


@pytest.fixture
def mock_github_client():
    """Mock GitHubClient."""
    return MagicMock()


@pytest.fixture
def governance_config():
    """Minimal governance config granting alice maintainer rights on repo-one."""
    return {
        "teams": [
            {"name": "repo-one-maintainers", "maintainers": ["alice"], "members": []},
        ],
        "repositories": [
            {"name": "repo-one", "teams": {"repo-one-maintainers": "maintain"}},
        ],
    }


@pytest.fixture
def synthetic_activity():
    """Synthetic contributor activity spanning maintainer and general-user roles."""
    return [
        _test_activity("hiero-ledger/repo-one", "authored_pull_request", "alice", days_ago=10),
        _test_activity("hiero-ledger/repo-one", "merged_pull_request", "alice", days_ago=9),
        _test_activity("hiero-ledger/repo-one", "authored_issue", "bob", days_ago=20),
        _test_activity("hiero-ledger/repo-two", "reviewed_pull_request", "carol", days_ago=5),
    ]


def _patch_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mock_client,
    config: dict,
    records: list[ContributorActivityRecord],
) -> None:
    """Redirect the pipeline preamble to tmp_path and stub the external fetches."""
    monkeypatch.setattr(
        "hiero_analytics.pipelines.maintainer_pipeline.org_context",
        lambda _org: (mock_client, tmp_path / "data", tmp_path / "charts"),
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.maintainer_pipeline.fetch_governance_config",
        lambda *_a, **_k: config,
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.maintainer_pipeline.load_contributor_activity",
        lambda _client, _org: records,
    )


# Tests


def test_main_creates_output_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_github_client,
    governance_config,
    synthetic_activity,
):
    """Running main() should create the pipeline CSV tables and stacked-bar charts."""
    _patch_pipeline(monkeypatch, tmp_path, mock_github_client, governance_config, synthetic_activity)

    runner.main()

    data_dir = tmp_path / "data"
    charts_dir = tmp_path / "charts"

    expected_csvs = [
        "maintainer_activity_events.csv",
        "maintainer_pipeline_yearly.csv",
        "maintainer_pipeline_monthly.csv",
        "maintainer_pipeline_weekly.csv",
        "maintainer_pipeline_by_repo.csv",
    ]
    expected_charts = [
        "maintainer_pipeline_yearly.png",
        "maintainer_pipeline_monthly.png",
        "maintainer_pipeline_weekly.png",
        "maintainer_pipeline_by_repo.png",
    ]

    for csv_file in expected_csvs:
        csv_path = data_dir / csv_file
        assert csv_path.exists(), f"CSV {csv_file} not created"
        assert os.path.getsize(csv_path) > 0, f"CSV {csv_file} is empty"

    for chart_file in expected_charts:
        chart_path = charts_dir / chart_file
        assert chart_path.exists(), f"Chart {chart_file} not created"
        assert os.path.getsize(chart_path) > 0, f"Chart {chart_file} is empty"


def test_main_handles_empty_activity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_github_client,
    governance_config,
):
    """Running main() with no contributor activity should not crash.

    Empty pipelines still write header-only CSV tables, while the chart
    renders are skipped via plot_and_save's empty-frame guard.
    """
    _patch_pipeline(monkeypatch, tmp_path, mock_github_client, governance_config, records=[])

    # Should not raise an exception
    runner.main()

    data_dir = tmp_path / "data"
    charts_dir = tmp_path / "charts"

    assert (data_dir / "maintainer_activity_events.csv").exists()
    assert (data_dir / "maintainer_pipeline_yearly.csv").exists()
    assert not (charts_dir / "maintainer_pipeline_yearly.png").exists()
