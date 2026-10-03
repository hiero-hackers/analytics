"""Pure-function tests for the contributor-profiles runner.

These exercise the data-shaping helpers (no GitHub) by importing
the runner module directly, mirroring the discord-runner test approach.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import hiero_analytics.pipelines.contributor_profiles as runner

# ---------------------------------------------------------------------------
# classify_contributor
# ---------------------------------------------------------------------------


def test_classify_contributor_uses_highest_difficulty_present():
    """The highest difficulty with any activity wins."""
    assert runner.classify_contributor({"Advanced": 1}) == "Advanced contributor"
    assert runner.classify_contributor({"Intermediate": 2}) == "Intermediate contributor"
    assert runner.classify_contributor({"Beginner": 3}) == "Beginner contributor"


def test_classify_contributor_defaults_to_gfi():
    """A contributor with no beginner-or-above activity is a GFI contributor."""
    assert runner.classify_contributor({"Good First Issue": 5}) == "GFI contributor"
    assert runner.classify_contributor({}) == "GFI contributor"


def test_classify_contributor_precedence_advanced_over_lower():
    """Advanced outranks intermediate/beginner when several are present."""
    row = {"Advanced": 1, "Intermediate": 9, "Beginner": 9}
    assert runner.classify_contributor(row) == "Advanced contributor"


# ---------------------------------------------------------------------------
# build_max_difficulty_distribution
# ---------------------------------------------------------------------------


def test_max_difficulty_counts_each_contributor_once_at_their_peak():
    """A contributor is counted once, at the highest difficulty they reached."""
    pr_df = pd.DataFrame(
        {
            "author": ["alice", "alice", "bob", "carol"],
            "issue_labels": [["beginner"], ["advanced"], ["beginner"], ["good first issue"]],
        }
    )

    result = runner.build_max_difficulty_distribution(pr_df)
    counts = dict(zip(result["difficulty"].astype(str), result["count"], strict=True))

    # alice peaks at Advanced (not double-counted as Beginner too)
    assert counts == {"Good First Issue": 1, "Beginner": 1, "Advanced": 1}
    # one row per distinct contributor, never per PR
    assert int(result["count"].sum()) == pr_df["author"].nunique()


def test_max_difficulty_drops_unknown_only_contributors():
    """Contributors whose PRs carry no difficulty label fall outside the order."""
    pr_df = pd.DataFrame(
        {
            "author": ["alice", "dave"],
            "issue_labels": [["beginner"], ["bug"]],
        }
    )

    result = runner.build_max_difficulty_distribution(pr_df)
    counts = dict(zip(result["difficulty"].astype(str), result["count"], strict=True))

    # dave (bug-only -> Unknown peak) is excluded; only alice's Beginner remains
    assert counts == {"Beginner": 1}
    assert int(result["count"].sum()) == 1


def test_max_difficulty_orders_low_to_high():
    """Result rows follow the GFI -> Advanced difficulty order."""
    pr_df = pd.DataFrame(
        {
            "author": ["a", "b", "c", "d"],
            "issue_labels": [["advanced"], ["good first issue"], ["intermediate"], ["beginner"]],
        }
    )

    result = runner.build_max_difficulty_distribution(pr_df)

    assert list(result["difficulty"].astype(str)) == [
        "Good First Issue",
        "Beginner",
        "Intermediate",
        "Advanced",
    ]


# ---------------------------------------------------------------------------
# build_avg_contribution_mix
# ---------------------------------------------------------------------------


def test_avg_contribution_mix_averages_within_contributor_type():
    """Per-difficulty counts are averaged across contributors of the same type."""
    pr_df = pd.DataFrame(
        {
            "author": ["alice", "carol", "carol", "carol"],
            "issue_labels": [
                ["beginner"],  # alice: Beginner=1
                ["beginner"],  # carol: Beginner=3
                ["beginner"],
                ["beginner"],
            ],
        }
    )

    avg = runner.build_avg_contribution_mix(pr_df).set_index("contributor_type")

    # both alice (1) and carol (3) are Beginner contributors -> mean Beginner = 2
    assert avg.loc["Beginner contributor", "Beginner"] == 2.0
    assert avg.loc["Beginner contributor", "total"] == 2.0


def test_avg_contribution_mix_classifies_by_peak_difficulty():
    """A contributor with mixed PRs is typed by their highest difficulty."""
    pr_df = pd.DataFrame(
        {
            "author": ["alice", "alice"],
            "issue_labels": [["beginner"], ["advanced"]],
        }
    )

    avg = runner.build_avg_contribution_mix(pr_df)

    assert set(avg["contributor_type"]) == {"Advanced contributor"}


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def test_main_writes_both_tables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """main() writes the average-mix and max-difficulty tables next to each other."""
    from datetime import UTC, datetime

    from hiero_analytics.data_sources.models import PullRequestDifficultyRecord

    def _pr(number: int, author: str, labels: list[str]) -> PullRequestDifficultyRecord:
        merged = datetime(2025, 1, number, tzinfo=UTC)
        return PullRequestDifficultyRecord(
            repo="org/repo",
            pr_number=number,
            pr_created_at=merged,
            pr_merged_at=merged,
            pr_additions=1,
            pr_deletions=1,
            pr_changed_files=1,
            issue_number=number,
            issue_labels=labels,
            author=author,
        )

    prs = [_pr(1, "alice", ["beginner"]), _pr(2, "alice", ["advanced"]), _pr(3, "bob", ["good first issue"])]
    monkeypatch.setattr(runner, "repo_context", lambda _org, _repo: (object(), tmp_path))
    monkeypatch.setattr(runner, "fetch_repo_merged_pr_difficulty_graphql", lambda *_a, **_k: prs)

    runner.main("org", "repo")

    mix = pd.read_csv(tmp_path / "avg_contribution_mix_by_type.csv")
    assert set(mix["contributor_type"]) == {"Advanced contributor", "GFI contributor"}

    peak = pd.read_csv(tmp_path / "max_difficulty_distribution.csv")
    assert list(peak.columns) == ["difficulty", "count"]
    assert dict(zip(peak["difficulty"], peak["count"], strict=True)) == {"Good First Issue": 1, "Advanced": 1}
