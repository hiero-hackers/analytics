"""Integration tests for the Hiero Hackers organization analytics runner."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import hiero_analytics.pipelines.org_overview as runner
from hiero_analytics.data_sources.models import (
    ContributorActivityRecord,
    RepositoryRecord,
)

# Test data factories


def _test_repo(name: str, pushed_at=None, language=None) -> RepositoryRecord:
    """Create a test repository record."""
    from datetime import UTC, datetime, timedelta

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
    from datetime import UTC, datetime

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
    """Running main() should create the expected data files."""
    # Redirect paths to tmp_path and stub the GitHub client
    monkeypatch.setattr(
        "hiero_analytics.pipelines.org_overview.org_context",
        lambda _org: (mock_github_client, tmp_path / "data"),
    )

    # Mock GitHub API calls
    monkeypatch.setattr(
        "hiero_analytics.pipelines.org_overview.fetch_org_repos_graphql",
        lambda _client, _org: synthetic_repos,
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.org_overview.load_contributor_activity",
        lambda _client, _org: synthetic_activity,
    )

    # Run the main function
    runner.main()

    # Assert expected output files exist
    data_dir = tmp_path / "data"

    expected_csvs = [
        "language_distribution.csv",
        "push_activity.csv",
        "contributor_counts.csv",
    ]

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
    # Redirect paths to tmp_path and stub the GitHub client
    monkeypatch.setattr(
        "hiero_analytics.pipelines.org_overview.org_context",
        lambda _org: (mock_github_client, tmp_path / "data"),
    )

    # Mock GitHub API calls
    monkeypatch.setattr(
        "hiero_analytics.pipelines.org_overview.fetch_org_repos_graphql",
        lambda _client, _org: synthetic_repos,
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.org_overview.load_contributor_activity",
        lambda _client, _org: [],  # Empty activity
    )

    # Should not raise an exception
    runner.main()

    # Core CSVs should still exist; the empty contributor table is skipped.
    data_dir = tmp_path / "data"
    assert (data_dir / "language_distribution.csv").exists()
    assert (data_dir / "push_activity.csv").exists()
    assert not (data_dir / "contributor_counts.csv").exists()


def test_main_with_empty_repos(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_github_client,
):
    """Running main() with empty repos should not crash."""
    # Redirect paths to tmp_path and stub the GitHub client
    monkeypatch.setattr(
        "hiero_analytics.pipelines.org_overview.org_context",
        lambda _org: (mock_github_client, tmp_path / "data"),
    )

    # Mock GitHub API calls
    monkeypatch.setattr(
        "hiero_analytics.pipelines.org_overview.fetch_org_repos_graphql",
        lambda _client, _org: [],  # Empty repos
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.org_overview.load_contributor_activity",
        lambda _client, _org: [],
    )

    # Should not raise an exception
    runner.main()


def test_contributor_counts_use_the_persisted_dataset_within_six_months(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_github_client,
    synthetic_repos,
):
    """The card reads the org's persisted activity, keeping only the last ~six months."""
    import dataclasses
    from datetime import UTC, datetime, timedelta

    import pandas as pd

    recent = _test_activity("hiero-hackers/sdk-python", "alice")
    old = dataclasses.replace(
        _test_activity("hiero-hackers/sdk-java", "bob"),
        occurred_at=datetime.now(UTC) - timedelta(days=runner.CONTRIBUTOR_WINDOW_DAYS + 1),
    )
    loaded = []
    monkeypatch.setattr(runner, "org_context", lambda _org: (mock_github_client, tmp_path / "data"))
    monkeypatch.setattr(runner, "fetch_org_repos_graphql", lambda _client, _org: synthetic_repos)
    monkeypatch.setattr(runner, "load_contributor_activity", lambda _client, org: loaded.append(org) or [recent, old])

    runner.main("hiero-hackers")

    assert loaded == ["hiero-hackers"]
    counts = pd.read_csv(tmp_path / "data" / "contributor_counts.csv")
    assert counts.to_dict("records") == [{"repo": "hiero-hackers/sdk-python", "contributors": 1}]


def test_main_without_an_org_builds_the_orgs_with_the_capability(monkeypatch):
    """Run alone, it builds the rendered orgs that have org_overview, not the primary org."""
    from hiero_analytics.config import orgs
    from hiero_analytics.config.orgs import OrgProfile

    monkeypatch.setattr(
        orgs, "ORGS", (OrgProfile(name="primary-org"), OrgProfile(name="overview-org", org_overview=True, extra=True))
    )
    monkeypatch.setenv("GITHUB_ORG", "primary-org")
    built = []
    monkeypatch.setattr(runner, "_build_org_overview", built.append)

    runner.main()
    runner.main("primary-org")

    assert built == ["overview-org", "primary-org"]
