"""Integration tests for the contributor-activity tables pipeline runner."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import matplotlib
import pytest

matplotlib.use("Agg")

import hiero_analytics.pipelines.contributor_activity as runner
from hiero_analytics.data_sources.models import (
    ContributorActivityRecord,
    IssueTimelineEventRecord,
)

ORG = "test-org"

# Test data factories


def _test_activity(
    repo: str,
    actor: str,
    activity_type: str = "authored_pull_request",
    days_ago: int = 1,
) -> ContributorActivityRecord:
    """Create a test contributor activity record."""
    return ContributorActivityRecord(
        repo=repo,
        activity_type=activity_type,
        actor=actor,
        occurred_at=datetime.now(UTC) - timedelta(days=days_ago),
        target_type="pull_request",
        target_number=1,
        target_author=actor,
    )


def _test_label_event(repo: str, actor: str, days_ago: int = 1) -> IssueTimelineEventRecord:
    """Create a test issue label event record."""
    return IssueTimelineEventRecord(
        repo=repo,
        issue_number=1,
        event_type="labeled",
        occurred_at=datetime.now(UTC) - timedelta(days=days_ago),
        label="bug",
        actor=actor,
    )


# Fixtures


@pytest.fixture
def mock_github_client():
    """Mock GitHubClient."""
    return MagicMock()


@pytest.fixture
def synthetic_activity():
    """Synthetic contributor activity data spanning two repos with a shared contributor."""
    return [
        _test_activity(f"{ORG}/repo-a", "alice", "authored_pull_request"),
        _test_activity(f"{ORG}/repo-a", "bob", "reviewed_pull_request"),
        _test_activity(f"{ORG}/repo-a", "bob", "merged_pull_request"),
        _test_activity(f"{ORG}/repo-b", "alice", "authored_issue"),
        _test_activity(f"{ORG}/repo-b", "charlie", "authored_pull_request"),
    ]


@pytest.fixture
def synthetic_label_events():
    """Synthetic issue label events with actors."""
    return [
        _test_label_event(f"{ORG}/repo-a", "bob"),
        _test_label_event(f"{ORG}/repo-b", "alice"),
    ]


def _patch_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mock_client,
    activity,
    label_events,
) -> None:
    """Redirect all pipeline inputs and output directories to tmp_path."""
    monkeypatch.setattr(
        "hiero_analytics.pipelines.contributor_activity.org_context",
        lambda _org: (mock_client, tmp_path / "data", tmp_path / "charts"),
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.contributor_activity.load_contributor_activity",
        lambda _client, _org: activity,
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.contributor_activity.load_issue_label_events",
        lambda _client, _org: label_events,
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.contributor_activity.fetch_org_merged_pr_difficulty_graphql",
        lambda _client, _org, **_k: [],
    )

    def _fake_repo_dirs(repo: str) -> tuple[Path, Path]:
        """Create and return per-repo output dirs under tmp_path."""
        slug = repo.replace("/", "_")
        repo_data_dir = tmp_path / "repo" / slug / "data"
        repo_charts_dir = tmp_path / "repo" / slug / "charts"
        repo_data_dir.mkdir(parents=True, exist_ok=True)
        repo_charts_dir.mkdir(parents=True, exist_ok=True)
        return repo_data_dir, repo_charts_dir

    monkeypatch.setattr(
        "hiero_analytics.pipelines.contributor_activity.ensure_repo_dirs",
        _fake_repo_dirs,
    )


# Tests


def test_main_creates_output_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_github_client,
    synthetic_activity,
    synthetic_label_events,
):
    """Running main() should create the profile CSVs and the contributor network chart."""
    _patch_pipeline(monkeypatch, tmp_path, mock_github_client, synthetic_activity, synthetic_label_events)

    runner.main(ORG)

    data_dir = tmp_path / "data"
    expected_csvs = [
        "contributor_activity_profiles.csv",
        "contributor_activity_profiles_30d.csv",
        "contributor_activity_profiles_90d.csv",
        "contributor_activity_profiles_180d.csv",
        "contributor_activity_profiles_365d.csv",
        "contributor_activity_profiles_all.csv",
    ]
    for csv_file in expected_csvs:
        csv_path = data_dir / csv_file
        assert csv_path.exists(), f"CSV {csv_file} not created"
        assert os.path.getsize(csv_path) > 0, f"CSV {csv_file} is empty"

    # Per-repo profile tables are written under each repo's (patched) data dir.
    for repo in (f"{ORG}/repo-a", f"{ORG}/repo-b"):
        slug = repo.replace("/", "_")
        repo_csv = tmp_path / "repo" / slug / "data" / "contributor_activity_profiles.csv"
        assert repo_csv.exists(), f"Per-repo CSV for {repo} not created"
        assert os.path.getsize(repo_csv) > 0, f"Per-repo CSV for {repo} is empty"

    network_chart = tmp_path / "charts" / "all_network.png"
    assert network_chart.exists(), "Contributor network chart not created"
    assert os.path.getsize(network_chart) > 0, "Contributor network chart is empty"


def test_main_handles_empty_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_github_client,
):
    """Running main() with no activity or label events should not crash."""
    _patch_pipeline(monkeypatch, tmp_path, mock_github_client, [], [])

    runner.main(ORG)

    # The org-wide profile table is still written (headers only).
    assert (tmp_path / "data" / "contributor_activity_profiles.csv").exists()
