"""Pure-function tests for the contributor-profiles runner.

These exercise the data-shaping helpers (no GitHub, no plotting) by importing
the runner module directly, mirroring the discord-runner test approach.
"""

from __future__ import annotations

import pandas as pd

import hiero_analytics.run_contributor_profiles_repo as runner

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
