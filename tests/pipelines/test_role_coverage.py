"""Integration tests for the role-coverage pipeline orchestration (``main``)."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import matplotlib
import pytest

matplotlib.use("Agg")

import hiero_analytics.pipelines.role_coverage as runner
from hiero_analytics.data_sources.models import (
    ContributorActivityRecord,
    IssueTimelineEventRecord,
)

TEST_ORG = "test-org"

# Test data factories


def _test_activity(
    repo: str,
    actor: str,
    activity_type: str = "authored_pull_request",
    days_ago: int = 5,
    number: int = 1,
) -> ContributorActivityRecord:
    """Create a synthetic contributor activity record ``days_ago`` days in the past."""
    return ContributorActivityRecord(
        repo=repo,
        activity_type=activity_type,
        actor=actor,
        occurred_at=datetime.now(UTC) - timedelta(days=days_ago),
        target_type="pull_request",
        target_number=number,
    )


def _test_label_event(repo: str, actor: str, days_ago: int = 5) -> IssueTimelineEventRecord:
    """Create a synthetic issue label event ``days_ago`` days in the past."""
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
def governance_config() -> dict:
    """Minimal governance config: two repos, a maintain team, a write team, and tsc."""
    return {
        "teams": [
            {"name": "sdk-python-maintainers", "maintainers": ["alice"], "members": ["bob"]},
            {"name": "sdk-python-committers", "maintainers": [], "members": ["carol"]},
            {"name": "tsc", "maintainers": ["alice"], "members": []},
        ],
        "repositories": [
            {
                "name": "sdk-python",
                "teams": {"sdk-python-maintainers": "maintain", "sdk-python-committers": "write"},
            },
            {"name": "sdk-java", "teams": {"sdk-python-maintainers": "maintain"}},
        ],
    }


@pytest.fixture
def synthetic_activity() -> list[ContributorActivityRecord]:
    """Recent and older activity for the role-holders across both governed repos."""
    return [
        _test_activity(f"{TEST_ORG}/sdk-python", "alice", "authored_pull_request", days_ago=3, number=1),
        _test_activity(f"{TEST_ORG}/sdk-python", "alice", "merged_pull_request", days_ago=2, number=2),
        _test_activity(f"{TEST_ORG}/sdk-python", "bob", "reviewed_pull_request", days_ago=10, number=1),
        _test_activity(f"{TEST_ORG}/sdk-python", "carol", "authored_issue", days_ago=200, number=3),
        _test_activity(f"{TEST_ORG}/sdk-java", "alice", "authored_pull_request", days_ago=7, number=4),
        _test_activity(f"{TEST_ORG}/sdk-java", "bob", "reviewed_pull_request", days_ago=8, number=4),
    ]


@pytest.fixture
def synthetic_label_events() -> list[IssueTimelineEventRecord]:
    """A single label event so the label-derived profile columns are exercised."""
    return [_test_label_event(f"{TEST_ORG}/sdk-python", "alice", days_ago=4)]


def _patch_pipeline(monkeypatch, tmp_path, config, activity, label_events):
    """Redirect every external call ``main()`` makes to synthetic in-memory data."""
    mock_client = MagicMock()
    monkeypatch.setattr(
        "hiero_analytics.pipelines.role_coverage.org_context",
        lambda _org: (mock_client, tmp_path / "data", tmp_path / "charts"),
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.role_coverage.fetch_governance_config",
        lambda *_a, **_k: config,
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.role_coverage.load_contributor_activity",
        lambda _client, _org: activity,
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.role_coverage.load_issue_label_events",
        lambda _client, _org: label_events,
    )

    def _fake_repo_dirs(repo_full: str) -> tuple[Path, Path]:
        slug = repo_full.replace("/", "_")
        repo_data_dir = tmp_path / "repo_data" / slug
        repo_charts_dir = tmp_path / "repo_charts" / slug
        repo_data_dir.mkdir(parents=True, exist_ok=True)
        repo_charts_dir.mkdir(parents=True, exist_ok=True)
        return repo_data_dir, repo_charts_dir

    monkeypatch.setattr("hiero_analytics.pipelines.role_coverage.ensure_repo_dirs", _fake_repo_dirs)


# Tests


def test_main_creates_output_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    governance_config,
    synthetic_activity,
    synthetic_label_events,
):
    """Running main() should create the key org-level and per-repo coverage tables."""
    _patch_pipeline(monkeypatch, tmp_path, governance_config, synthetic_activity, synthetic_label_events)

    runner.main(TEST_ORG)

    data_dir = tmp_path / "data"
    expected_csvs = [
        "role_coverage_all.csv",
        "role_coverage_all_90d.csv",
        "team_activity_summary.csv",
        "team_activity_by_repo.csv",
        "role_coverage_globally_quiet.csv",
        "repo_activity_overview.csv",
        "tsc_activity_by_repo.csv",
    ]
    for csv_file in expected_csvs:
        csv_path = data_dir / csv_file
        assert csv_path.exists(), f"CSV {csv_file} not created"
        assert os.path.getsize(csv_path) > 0, f"CSV {csv_file} is empty"

    # The combined coverage table has one row per (repo, holder) pair.
    coverage = (data_dir / "role_coverage_all.csv").read_text(encoding="utf-8")
    assert "alice" in coverage
    assert f"{TEST_ORG}/sdk-python" in coverage

    # Legacy per-repo files are written through the patched ensure_repo_dirs.
    repo_data_dir = tmp_path / "repo_data" / f"{TEST_ORG}_sdk-python"
    assert (repo_data_dir / "role_coverage.csv").exists()
    assert (repo_data_dir / "role_promotion_candidates.csv").exists()


def test_main_handles_empty_activity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    governance_config,
):
    """Running main() with no recorded activity should not crash.

    Role-holders exist in governance but have no activity anywhere, so every
    holder is quiet and the globally-quiet table still lists them.
    """
    _patch_pipeline(monkeypatch, tmp_path, governance_config, [], [])

    runner.main(TEST_ORG)

    data_dir = tmp_path / "data"
    assert (data_dir / "role_coverage_all.csv").exists()
    assert (data_dir / "team_activity_summary.csv").exists()
    quiet = (data_dir / "role_coverage_globally_quiet.csv").read_text(encoding="utf-8")
    assert "alice" in quiet
