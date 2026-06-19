"""Integration tests for the Hiero Hackers organization analytics runner."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import matplotlib
import pytest

matplotlib.use("Agg")

import hiero_analytics.run_hiero_hackers_org as runner
from hiero_analytics.data_sources.models import (
    ContributorActivityRecord,
    RepositoryRecord,
)


# Test data factories


def _test_repo(name: str, pushed_at=None, language=None) -> RepositoryRecord:
    """Create a test repository record."""
    from datetime import datetime, UTC, timedelta
    
    if pushed_at is None:
        pushed_at = datetime.now(UTC) - timedelta(days=5)
    
    return RepositoryRecord(
        full_name=f"hiero-hackers/{name}",
        name=name,
        owner="hiero-hackers",
        pushed_at=pushed_at,
        language=language,
    )


def _test_activity(repo: str, actor: str) -> ContributorActivityRecord:
    """Create a test contributor activity record."""
    from datetime import datetime, UTC
    
    return ContributorActivityRecord(
        repo=repo,
        activity_type="OPENED",
        actor=actor,
        occurred_at=datetime.now(UTC),
        target_type="ISSUE",
        target_number=1,
    )


# Fixtures


@pytest.fixture
def mock_github_client():
    """Mock GitHubClient."""
    return MagicMock()


@pytest.fixture
def synthetic_repos():
    """Synthetic repository data."""
    return [
        _test_repo("sdk-python", language="Python"),
        _test_repo("sdk-java", language="Java"),
        _test_repo("sdk-go", language="Go"),
        _test_repo("hips", language="Markdown"),
    ]


@pytest.fixture
def synthetic_activity():
    """Synthetic contributor activity data."""
    return [
        _test_activity("hiero-hackers/sdk-python", "alice"),
        _test_activity("hiero-hackers/sdk-python", "bob"),
        _test_activity("hiero-hackers/sdk-java", "charlie"),
        _test_activity("hiero-hackers/sdk-java", "alice"),
        _test_activity("hiero-hackers/sdk-go", "diana"),
        _test_activity("hiero-hackers/hips", "eve"),
    ]


# Tests


def test_main_creates_output_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_github_client,
    synthetic_repos,
    synthetic_activity,
):
    """Running main() should create expected chart and data files."""
    # Redirect paths to tmp_path
    monkeypatch.setattr(
        "hiero_analytics.run_hiero_hackers_org.ensure_org_dirs",
        lambda org: (tmp_path / "data", tmp_path / "charts"),
    )
    
    # Mock GitHub API calls
    monkeypatch.setattr(
        "hiero_analytics.run_hiero_hackers_org.fetch_org_repos_graphql",
        lambda client, org: synthetic_repos,
    )
    monkeypatch.setattr(
        "hiero_analytics.run_hiero_hackers_org.fetch_org_contributor_activity_graphql",
        lambda client, org: synthetic_activity,
    )
    
    # Mock GitHubClient initialization
    monkeypatch.setattr(
        "hiero_analytics.run_hiero_hackers_org.GitHubClient",
        lambda: mock_github_client,
    )
    
    # Run the main function
    runner.main()
    
    # Assert expected output files exist
    charts_dir = tmp_path / "charts"
    data_dir = tmp_path / "data"
    
    expected_charts = [
        "language_distribution.png",
        "push_activity.png",
        "contributor_counts.png",
    ]
    expected_csvs = [
        "language_distribution.csv",
        "push_activity.csv",
        "contributor_counts.csv",
    ]
    
    for chart_file in expected_charts:
        chart_path = charts_dir / chart_file
        assert chart_path.exists(), f"Chart {chart_file} not created"
        assert os.path.getsize(chart_path) > 0, f"Chart {chart_file} is empty"
    
    for csv_file in expected_csvs:
        csv_path = data_dir / csv_file
        assert csv_path.exists(), f"CSV {csv_file} not created"
        assert os.path.getsize(csv_path) > 0, f"CSV {csv_file} is empty"


def test_main_handles_empty_activity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_github_client,
    synthetic_repos,
):
    """Running main() with empty activity should not crash."""
    # Redirect paths to tmp_path
    monkeypatch.setattr(
        "hiero_analytics.run_hiero_hackers_org.ensure_org_dirs",
        lambda org: (tmp_path / "data", tmp_path / "charts"),
    )
    
    # Mock GitHub API calls
    monkeypatch.setattr(
        "hiero_analytics.run_hiero_hackers_org.fetch_org_repos_graphql",
        lambda client, org: synthetic_repos,
    )
    monkeypatch.setattr(
        "hiero_analytics.run_hiero_hackers_org.fetch_org_contributor_activity_graphql",
        lambda client, org: [],  # Empty activity
    )
    
    # Mock GitHubClient initialization
    monkeypatch.setattr(
        "hiero_analytics.run_hiero_hackers_org.GitHubClient",
        lambda: mock_github_client,
    )
    
    # Should not raise an exception
    runner.main()
    
    # Core charts should still exist
    charts_dir = tmp_path / "charts"
    assert (charts_dir / "language_distribution.png").exists()
    assert (charts_dir / "push_activity.png").exists()


def test_main_with_empty_repos(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_github_client,
):
    """Running main() with empty repos should not crash."""
    # Redirect paths to tmp_path
    monkeypatch.setattr(
        "hiero_analytics.run_hiero_hackers_org.ensure_org_dirs",
        lambda org: (tmp_path / "data", tmp_path / "charts"),
    )
    
    # Mock GitHub API calls
    monkeypatch.setattr(
        "hiero_analytics.run_hiero_hackers_org.fetch_org_repos_graphql",
        lambda client, org: [],  # Empty repos
    )
    monkeypatch.setattr(
        "hiero_analytics.run_hiero_hackers_org.fetch_org_contributor_activity_graphql",
        lambda client, org: [],
    )
    
    # Mock GitHubClient initialization
    monkeypatch.setattr(
        "hiero_analytics.run_hiero_hackers_org.GitHubClient",
        lambda: mock_github_client,
    )
    
    # Should not raise an exception
    runner.main()
