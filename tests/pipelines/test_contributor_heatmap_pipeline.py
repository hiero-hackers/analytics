"""Integration tests for the contributor-activity heatmap pipeline runner."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

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
    governance: dict | None = None,
) -> Path:
    """Stub the client, governance config and dataset load; return the org's output dir."""
    org_data_dir = tmp_path / "data" / ORG
    org_data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(runner, "org_context", lambda _org: (mock_client, org_data_dir))
    monkeypatch.setattr(runner, "fetch_governance_config", lambda *_a, **_k: governance or {})
    monkeypatch.setattr(runner, "load_contributor_activity", lambda _client, _org: activity)
    return org_data_dir


# Tests


def test_main_creates_output_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_github_client,
    synthetic_activity,
):
    """Running main() builds the heatmap CSV for the given org, and only that org."""
    org_data_dir = _patch_pipeline(monkeypatch, tmp_path, mock_github_client, synthetic_activity)

    runner.main(ORG)

    csv_path = org_data_dir / "contributor_activity_heatmap.csv"
    assert csv_path.exists()
    assert os.path.getsize(csv_path) > 0
    heatmap = pd.read_csv(csv_path)
    assert set(heatmap["contributor name"]) == {"alice", "bob", "charlie"}
    assert any(re.fullmatch(r"\d{4}-\d{2}", column) for column in heatmap.columns)
    # The orchestrator renders other orgs; this pipeline never loops over them itself.
    assert [path.name for path in (tmp_path / "data").iterdir()] == [ORG]


def test_ungoverned_org_gets_no_role_labels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_github_client,
    synthetic_activity,
):
    """An org with no governance config labels everyone a general user."""
    org_data_dir = _patch_pipeline(monkeypatch, tmp_path, mock_github_client, synthetic_activity)

    runner.main(ORG)

    heatmap = pd.read_csv(org_data_dir / "contributor_activity_heatmap.csv")
    assert set(heatmap["role"]) == {"General User"}


def test_governed_org_labels_contributors_by_role(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_github_client,
    synthetic_activity,
):
    """A governed org's config labels its role holders, resolved against that org's teams."""
    governance = {
        "teams": [{"name": "repo-a-maintainers", "maintainers": ["bob"], "members": []}],
        "repositories": [{"name": "repo-a", "teams": {"repo-a-maintainers": "maintain"}}],
    }
    org_data_dir = _patch_pipeline(monkeypatch, tmp_path, mock_github_client, synthetic_activity, governance)

    runner.main(ORG)

    heatmap = pd.read_csv(org_data_dir / "contributor_activity_heatmap.csv").set_index("contributor name")
    assert heatmap.loc["bob", "role"] == "Maintainer"
    assert heatmap.loc["alice", "role"] == "General User"


def test_main_handles_empty_activity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_github_client,
):
    """Running main() with no activity records should not crash."""
    org_data_dir = _patch_pipeline(monkeypatch, tmp_path, mock_github_client, [])

    runner.main(ORG)

    # The (empty, headers-only) heatmap table is still written, month columns included.
    heatmap = pd.read_csv(org_data_dir / "contributor_activity_heatmap.csv")
    assert heatmap.empty
    assert any(re.fullmatch(r"\d{4}-\d{2}", column) for column in heatmap.columns)
