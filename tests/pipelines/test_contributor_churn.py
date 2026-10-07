"""Integration tests for the contributor churn and progression analysis runner."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

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
    """Redirect the output dir to tmp_path and stub the token, client, and PR fetch."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("hiero_analytics.pipelines.contributor_churn.GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(
        "hiero_analytics.pipelines.contributor_churn.repo_context",
        lambda _org, _repo: (MagicMock(), data_dir),
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.contributor_churn.fetch_repo_merged_pr_difficulty_graphql",
        lambda _client, **_kwargs: prs,
    )


# Tests


def test_main_writes_progression_and_churn_tables(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_prs,
):
    """Running main() should write the progression CSV and every churn table."""
    _patch_pipeline(monkeypatch, tmp_path, synthetic_prs)

    runner.main()

    data_dir = tmp_path / "data"

    # The author is a real column (not a dropped index) and only GFI starters remain.
    progression = pd.read_csv(data_dir / "contributor_progression.csv").set_index("author")
    assert set(progression.index) == {"alice", "bob"}
    assert progression.loc["alice", "max_level"] == "Advanced"
    assert progression.loc["alice", "pr_count"] == 4
    assert progression.loc["alice", "tenure_days"] == 60
    assert progression.loc["bob", "max_level"] == "Good First Issue"

    funnel = pd.read_csv(data_dir / "contributor_churn_funnel.csv")
    assert list(funnel.columns) == ["stage", "count"]
    assert dict(zip(funnel["stage"], funnel["count"], strict=True)) == {
        "GFI Starters": 2,
        "Progressed to Beginner+": 1,
        "Progressed to Intermediate+": 1,
        "Progressed to Advanced": 1,
    }

    # alice has 4 PRs, bob 1: both clear 1 PR, only alice clears 2..4.
    retention = pd.read_csv(data_dir / "contributor_retention.csv")
    assert list(retention.columns) == ["min_prs", "contributors"]
    assert retention["min_prs"].tolist() == [1, 2, 3, 4]
    assert retention["contributors"].tolist() == [2, 1, 1, 1]

    transitions = pd.read_csv(data_dir / "contributor_transitions.csv")
    assert list(transitions.columns) == ["from", "to", "count"]
    assert {(row["from"], row["to"]): row["count"] for _, row in transitions.iterrows()} == {
        ("Good First Issue", "Beginner"): 1,
        ("Beginner", "Intermediate"): 1,
        ("Intermediate", "Advanced"): 1,
    }

    # Sorted by difficulty order, not alphabetically.
    tenure = pd.read_csv(data_dir / "avg_tenure_by_level.csv")
    assert list(tenure.columns) == ["max_level", "avg_tenure_days"]
    assert tenure["max_level"].tolist() == ["Good First Issue", "Advanced"]
    assert tenure["avg_tenure_days"].tolist() == [0, 60]


def test_main_skips_transitions_csv_without_transitions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """A GFI starter who never progresses yields no transitions, so no transitions CSV."""
    _patch_pipeline(monkeypatch, tmp_path, [_test_pr(1, "bob", ["good first issue"], merged_days_ago=90)])

    runner.main()

    assert (tmp_path / "data" / "contributor_churn_funnel.csv").exists()
    assert not (tmp_path / "data" / "contributor_transitions.csv").exists()


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
    assert not (tmp_path / "data" / "contributor_churn_funnel.csv").exists()


def test_main_raises_on_empty_pr_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Running main() with no PR data should raise the documented ValueError."""
    _patch_pipeline(monkeypatch, tmp_path, prs=[])

    with pytest.raises(ValueError, match="No PR data found"):
        runner.main()
