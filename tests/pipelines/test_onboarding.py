"""Integration tests for the onboarding signal pipeline runner."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import matplotlib
import pytest

matplotlib.use("Agg")

import hiero_analytics.pipelines.onboarding as runner
from hiero_analytics.data_sources.models import IssueRecord, PullRequestDifficultyRecord

ORG = "test-org"
REPO = "repo-a"
FULL_REPO = f"{ORG}/{REPO}"

_BASE = datetime.now(UTC) - timedelta(days=100)

# Test data factories


def _test_issue(number: int, labels: list[str], created_days: int) -> IssueRecord:
    """Create a test issue record."""
    return IssueRecord(
        repo=FULL_REPO,
        number=number,
        title=f"Issue {number}",
        state="OPEN",
        created_at=_BASE + timedelta(days=created_days),
        closed_at=None,
        labels=labels,
    )


def _test_pr(
    pr_number: int,
    author: str,
    issue_labels: list[str],
    merged_days: int,
) -> PullRequestDifficultyRecord:
    """Create a test merged pull request record linked to a labelled issue."""
    return PullRequestDifficultyRecord(
        repo=FULL_REPO,
        pr_number=pr_number,
        pr_created_at=_BASE + timedelta(days=merged_days - 1),
        pr_merged_at=_BASE + timedelta(days=merged_days),
        pr_additions=10,
        pr_deletions=2,
        pr_changed_files=1,
        issue_number=pr_number,
        issue_labels=issue_labels,
        author=author,
    )


# Fixtures


@pytest.fixture
def mock_github_client():
    """Mock GitHubClient."""
    return MagicMock()


@pytest.fixture
def synthetic_issues():
    """Synthetic good-first-issue supply, created after the first merged PRs."""
    return [
        _test_issue(1, ["good first issue"], created_days=2),
        _test_issue(2, ["good first issue"], created_days=4),
        _test_issue(3, ["good first issue"], created_days=6),
    ]


@pytest.fixture
def synthetic_prs():
    """Synthetic merged PRs closing good-first-issues, by distinct contributors."""
    return [
        _test_pr(1, "alice", ["good first issue"], merged_days=1),
        _test_pr(2, "bob", ["good first issue"], merged_days=3),
        _test_pr(3, "charlie", ["good first issue"], merged_days=5),
    ]


def _patch_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mock_client,
    issues,
    prs,
) -> None:
    """Redirect the pipeline context to tmp_path and stub the GitHub fetches."""
    data_dir = tmp_path / "data"
    charts_dir = tmp_path / "charts"
    data_dir.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "hiero_analytics.pipelines.onboarding.repo_context",
        lambda _org, _repo: (mock_client, data_dir, charts_dir),
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.onboarding.fetch_repo_issues_graphql",
        lambda *_args, **_kwargs: issues,
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.onboarding.fetch_repo_merged_pr_difficulty_graphql",
        lambda *_args, **_kwargs: prs,
    )


# Tests


def test_main_creates_output_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_github_client,
    synthetic_issues,
    synthetic_prs,
):
    """Running main() should create the onboarding signal and per-difficulty charts."""
    _patch_pipeline(monkeypatch, tmp_path, mock_github_client, synthetic_issues, synthetic_prs)

    runner.main(ORG, REPO)

    charts_dir = tmp_path / "charts"
    expected_charts = [
        "onboarding_signal.png",
        # "good first issue" is also a difficulty level, so its efficiency chart renders.
        "good_first_issue.png",
    ]
    for chart_file in expected_charts:
        chart_path = charts_dir / chart_file
        assert chart_path.exists(), f"Chart {chart_file} not created"
        assert os.path.getsize(chart_path) > 0, f"Chart {chart_file} is empty"


def test_main_handles_empty_difficulty_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_github_client,
):
    """Running main() with no difficulty-labelled data should skip those charts, not crash.

    "good first issue candidate" counts as onboarding supply/demand but matches no
    difficulty level, so every per-difficulty subset is empty and is skipped.
    """
    issues = [
        _test_issue(1, ["good first issue candidate"], created_days=2),
        _test_issue(2, ["good first issue candidate"], created_days=4),
    ]
    prs = [
        _test_pr(1, "alice", ["good first issue candidate"], merged_days=1),
        _test_pr(2, "bob", ["good first issue candidate"], merged_days=3),
    ]
    _patch_pipeline(monkeypatch, tmp_path, mock_github_client, issues, prs)

    runner.main(ORG, REPO)

    charts_dir = tmp_path / "charts"
    assert (charts_dir / "onboarding_signal.png").exists()
    assert not (charts_dir / "good_first_issue.png").exists()
    assert not (charts_dir / "beginner.png").exists()


def test_main_skips_all_charts_on_empty_fetches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_github_client,
):
    """Running main() with entirely empty fetches skips every chart instead of crashing.

    A repo with no issues and no merged PRs is a data condition, not a bug — the
    signal chart is skipped with a log line (matching the per-difficulty guard),
    and plot_onboarding_signal itself still refuses empty input if called directly.
    """
    _patch_pipeline(monkeypatch, tmp_path, mock_github_client, [], [])

    runner.main(ORG, REPO)

    charts_dir = tmp_path / "charts"
    assert not (charts_dir / "onboarding_signal.png").exists()
    assert not any(charts_dir.iterdir())

    import pandas as pd

    with pytest.raises(ValueError, match="cannot be empty"):
        runner.plot_onboarding_signal(pd.DataFrame(), pd.DataFrame(), charts_dir / "x.png", title="t")
