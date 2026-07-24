"""Integration tests for the contributor-activity heatmap pipeline runner."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import matplotlib
import pytest

matplotlib.use("Agg")

import hiero_analytics.pipelines.contributor_heatmap as runner
from hiero_analytics.data_sources.models import ContributorActivityRecord

ORG = "test-org"

# Test data factories


def _test_activity(
    repo: str,
    actor: str,
    activity_type: str = "authored_pull_request",
    days_ago: int = 40,
) -> ContributorActivityRecord:
    """Create a test activity record inside the heatmap's recent-months window.

    The heatmap only scores fully completed months, so records default to ~40
    days ago (safely within the window, outside the current partial month).
    """
    return ContributorActivityRecord(
        repo=repo,
        activity_type=activity_type,
        actor=actor,
        occurred_at=datetime.now(UTC) - timedelta(days=days_ago),
        target_type="pull_request",
        target_number=1,
        target_author=actor,
    )


# Fixtures


@pytest.fixture
def mock_github_client():
    """Mock GitHubClient."""
    return MagicMock()


@pytest.fixture
def synthetic_activity():
    """Synthetic contributor activity data within the heatmap window."""
    return [
        _test_activity(f"{ORG}/repo-a", "alice", "authored_pull_request"),
        _test_activity(f"{ORG}/repo-a", "bob", "reviewed_pull_request"),
        _test_activity(f"{ORG}/repo-a", "bob", "merged_pull_request"),
        _test_activity(f"{ORG}/repo-b", "alice", "authored_issue", days_ago=45),
        _test_activity(f"{ORG}/repo-b", "charlie", "authored_pull_request", days_ago=45),
    ]


def _patch_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mock_client,
    activity,
) -> None:
    """Stub the GitHub client, governance config and dataset loads; redirect output dirs."""
    monkeypatch.setattr(
        "hiero_analytics.pipelines.contributor_heatmap.shared_client",
        lambda: mock_client,
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.contributor_heatmap.EXTRA_ORGS",
        ["hiero-hackers"],
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.contributor_heatmap.fetch_governance_config",
        lambda *_a, **_k: {},
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.contributor_heatmap.load_contributor_activity",
        lambda _client, _org: activity,
    )

    def _fake_org_dirs(org: str) -> tuple[Path, Path]:
        """Create and return per-org output dirs under tmp_path."""
        org_data_dir = tmp_path / "data" / org
        org_charts_dir = tmp_path / "charts" / org
        org_data_dir.mkdir(parents=True, exist_ok=True)
        org_charts_dir.mkdir(parents=True, exist_ok=True)
        return org_data_dir, org_charts_dir

    monkeypatch.setattr(
        "hiero_analytics.pipelines.contributor_heatmap.ensure_org_dirs",
        _fake_org_dirs,
    )


# Tests


def test_main_creates_output_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_github_client,
    synthetic_activity,
):
    """Running main() should build the heatmap CSV and PNG for the org and hiero-hackers."""
    _patch_pipeline(monkeypatch, tmp_path, mock_github_client, synthetic_activity)

    runner.main(ORG)

    # main() renders the given org plus the secondary hiero-hackers composition org.
    for org in (ORG, "hiero-hackers"):
        csv_path = tmp_path / "data" / org / "contributor_activity_heatmap.csv"
        assert csv_path.exists(), f"Heatmap CSV for {org} not created"
        assert os.path.getsize(csv_path) > 0, f"Heatmap CSV for {org} is empty"

        chart_path = tmp_path / "charts" / org / "contributor_activity_heatmap.png"
        assert chart_path.exists(), f"Heatmap chart for {org} not created"
        assert os.path.getsize(chart_path) > 0, f"Heatmap chart for {org} is empty"


def test_main_handles_empty_activity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_github_client,
):
    """Running main() with no activity records should not crash."""
    _patch_pipeline(monkeypatch, tmp_path, mock_github_client, [])

    runner.main(ORG)

    # The (empty, headers-only) heatmap table is still written; no chart is rendered.
    for org in (ORG, "hiero-hackers"):
        assert (tmp_path / "data" / org / "contributor_activity_heatmap.csv").exists()
        assert not (tmp_path / "charts" / org / "contributor_activity_heatmap.png").exists()
