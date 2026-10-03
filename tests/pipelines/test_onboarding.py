"""Integration tests for the onboarding signal pipeline runner."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

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
    data_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "hiero_analytics.pipelines.onboarding.repo_context",
        lambda _org, _repo: (mock_client, data_dir),
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


def test_main_writes_onboarding_tables(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_github_client,
    synthetic_issues,
    synthetic_prs,
):
    """Running main() should write the onboarding signal and the efficiency tables."""
    _patch_pipeline(monkeypatch, tmp_path, mock_github_client, synthetic_issues, synthetic_prs)

    runner.main(ORG, REPO)

    data_dir = tmp_path / "data"

    signal = pd.read_csv(data_dir / "onboarding_signal.csv")
    assert list(signal.columns) == ["series", "date", "count"]
    by_series = {name: group["count"].tolist() for name, group in signal.groupby("series")}
    # Three issues and three first-time contributors, each cumulative.
    assert by_series == {"onboarding_issues": [1, 2, 3], "contributors": [1, 2, 3]}

    # "good first issue" is also a difficulty level, so it gets an efficiency block.
    efficiency = pd.read_csv(data_dir / "onboarding_efficiency.csv")
    assert list(efficiency.columns) == ["difficulty", "date", "issue_count", "contrib_count"]
    assert set(efficiency["difficulty"]) == {"Good First Issue"}
    assert efficiency["issue_count"].tolist() == [1, 2, 3]
    # Each issue is paired with the contributor total at that date.
    assert efficiency["contrib_count"].tolist() == [1, 2, 3]


def test_main_handles_empty_difficulty_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_github_client,
):
    """Running main() with no difficulty-labelled data should skip the efficiency table, not crash.

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

    data_dir = tmp_path / "data"
    assert (data_dir / "onboarding_signal.csv").exists()
    assert not (data_dir / "onboarding_efficiency.csv").exists()


def test_main_skips_all_tables_on_empty_fetches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_github_client,
):
    """Running main() with entirely empty fetches writes nothing instead of crashing.

    A repo with no issues and no merged PRs is a data condition, not a bug.
    """
    _patch_pipeline(monkeypatch, tmp_path, mock_github_client, [], [])

    runner.main(ORG, REPO)

    assert not any((tmp_path / "data").iterdir())


def test_onboarding_signal_table_is_long_and_keeps_each_series_unresampled():
    """The two series stack long; neither is joined to the other's dates."""
    gfi_ts = pd.DataFrame({"created_at": pd.to_datetime(["2025-01-01", "2025-01-05"], utc=True), "count": [1, 2]})
    contrib_ts = pd.DataFrame({"pr_merged_at": pd.to_datetime(["2025-01-03"], utc=True), "count": [1]})

    table = runner.onboarding_signal_table(gfi_ts, contrib_ts)

    assert list(table.columns) == ["series", "date", "count"]
    assert table["series"].tolist() == ["onboarding_issues", "onboarding_issues", "contributors"]
    assert table["count"].tolist() == [1, 2, 1]
    assert len(table) == len(gfi_ts) + len(contrib_ts)


def _ts(date_col: str, dates: list[str], counts: list[int]) -> pd.DataFrame:
    """Build a cumulative time series frame."""
    return pd.DataFrame({date_col: pd.to_datetime(dates, utc=True), "count": counts})


def test_issue_vs_contributor_table_pairs_each_issue_with_latest_prior_contributors():
    """merge_asof pairs each issue date with the contributor count at or before it."""
    issues = _ts("created_at", ["2025-01-02", "2025-01-06"], [1, 2])
    contrib = _ts("pr_merged_at", ["2025-01-01", "2025-01-04"], [1, 2])

    table = runner.issue_vs_contributor_table(issues, contrib)

    assert list(table.columns) == ["date", "issue_count", "contrib_count"]
    assert table["issue_count"].tolist() == [1, 2]
    assert table["contrib_count"].tolist() == [1, 2]


def test_issue_vs_contributor_table_is_empty_without_overlap():
    """Issues that all predate every contributor have no match: empty frame, no error."""
    issues = _ts("created_at", ["2025-01-01"], [1])
    contrib = _ts("pr_merged_at", ["2025-02-01"], [1])

    assert runner.issue_vs_contributor_table(issues, contrib).empty


def test_issue_vs_contributor_table_sorts_unordered_input():
    """Inputs are sorted by date before joining."""
    issues = _ts("created_at", ["2025-01-06", "2025-01-02"], [2, 1])
    contrib = _ts("pr_merged_at", ["2025-01-04", "2025-01-01"], [2, 1])

    table = runner.issue_vs_contributor_table(issues, contrib)

    assert table["issue_count"].tolist() == [1, 2]
    assert table["contrib_count"].tolist() == [1, 2]


def test_issue_vs_contributor_table_honours_custom_date_columns():
    """Custom date column names are mapped onto the shared ``date`` column."""
    issues = _ts("opened", ["2025-01-02"], [1])
    contrib = _ts("merged", ["2025-01-01"], [1])

    table = runner.issue_vs_contributor_table(issues, contrib, issue_date_col="opened", contrib_date_col="merged")

    assert table["contrib_count"].tolist() == [1]
