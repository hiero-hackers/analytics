"""Integration tests for the contributor churn and progression analysis runner."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import matplotlib
import pytest

matplotlib.use("Agg")

import hiero_analytics.pipelines.contributor_churn as runner
from hiero_analytics.data_sources.models import PullRequestDifficultyRecord

# Test data factories


def _test_pr(
    pr_number: int,
    author: str,
    labels: list[str],
    merged_days_ago: int,
) -> PullRequestDifficultyRecord:
    """Create a merged PR difficulty record merged ``merged_days_ago`` days ago."""
    merged_at = datetime.now(UTC) - timedelta(days=merged_days_ago)
    return PullRequestDifficultyRecord(
        repo="hiero-ledger/repo-one",
        pr_number=pr_number,
        pr_created_at=merged_at - timedelta(days=1),
        pr_merged_at=merged_at,
        pr_additions=10,
        pr_deletions=2,
        pr_changed_files=1,
        issue_number=pr_number,
        issue_labels=labels,
        author=author,
    )


# Fixtures


@pytest.fixture
def synthetic_prs():
    """Synthetic merged PRs with a GFI starter progressing through every level."""
    return [
        # alice starts on a Good First Issue and progresses to Advanced.
        _test_pr(1, "alice", ["good first issue"], merged_days_ago=100),
        _test_pr(2, "alice", ["beginner"], merged_days_ago=80),
        _test_pr(3, "alice", ["intermediate"], merged_days_ago=60),
        _test_pr(4, "alice", ["advanced"], merged_days_ago=40),
        # bob starts on a Good First Issue and never progresses.
        _test_pr(5, "bob", ["good first issue"], merged_days_ago=90),
    ]


def _patch_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    prs: list[PullRequestDifficultyRecord],
) -> None:
    """Redirect output dirs to tmp_path and stub the token, client, and PR fetch."""
    data_dir = tmp_path / "data"
    charts_dir = tmp_path / "charts"
    data_dir.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("hiero_analytics.pipelines.contributor_churn.GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(
        "hiero_analytics.pipelines.contributor_churn.repo_context",
        lambda _org, _repo: (MagicMock(), data_dir, charts_dir),
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.contributor_churn.fetch_repo_merged_pr_difficulty_graphql",
        lambda _client, **_kwargs: prs,
    )


# Tests


def test_main_creates_output_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_prs,
):
    """Running main() should create the progression CSV and churn charts."""
    _patch_pipeline(monkeypatch, tmp_path, synthetic_prs)

    runner.main()

    data_dir = tmp_path / "data"
    charts_dir = tmp_path / "charts"

    csv_path = data_dir / "contributor_progression.csv"
    assert csv_path.exists(), "CSV contributor_progression.csv not created"
    assert os.path.getsize(csv_path) > 0, "CSV contributor_progression.csv is empty"

    expected_charts = [
        "contributor_churn_funnel.png",
        "contributor_retention.png",
        "contributor_transitions.png",
        "avg_tenure_by_level.png",
    ]
    for chart_file in expected_charts:
        chart_path = charts_dir / chart_file
        assert chart_path.exists(), f"Chart {chart_file} not created"
        assert os.path.getsize(chart_path) > 0, f"Chart {chart_file} is empty"


def test_main_handles_no_gfi_starters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Running main() with no GFI starters should return early without crashing."""
    prs = [_test_pr(1, "carol", ["intermediate"], merged_days_ago=30)]
    _patch_pipeline(monkeypatch, tmp_path, prs)

    # Should not raise an exception
    runner.main()

    # No GFI starters -> the pipeline exits before writing any outputs.
    assert not (tmp_path / "data" / "contributor_progression.csv").exists()
    assert not (tmp_path / "charts" / "contributor_churn_funnel.png").exists()


def test_main_raises_on_empty_pr_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Running main() with no PR data should raise the documented ValueError."""
    _patch_pipeline(monkeypatch, tmp_path, prs=[])

    with pytest.raises(ValueError, match="No PR data found"):
        runner.main()
