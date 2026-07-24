"""Tests for the contributor progression + level-transition analysis.

These pin the two behaviours most likely to regress silently: a PR closing
several issues counts once at its highest difficulty (no inflation), and
transitions are recorded only on genuine forward progress.
"""

from __future__ import annotations

import pandas as pd

from hiero_analytics.analysis.contributor_churn import compute_progression_stats, compute_transition_metrics


def _pr(author: str, pr_number: int, level: str, day: int) -> dict:
    """One (author, PR, level) row as prs_to_dataframe would emit."""
    return {
        "author": author,
        "pr_number": pr_number,
        "level": level,
        "pr_merged_at": pd.Timestamp("2026-01-01") + pd.Timedelta(days=day),
    }


def test_empty_input_returns_empty_frames():
    """No PR data yields empty frames rather than raising."""
    assert compute_progression_stats(pd.DataFrame()).empty
    assert compute_transition_metrics(pd.DataFrame()).empty


def test_progression_dedupes_multi_issue_prs_to_their_highest_level():
    """A PR linked to several issues counts once, at the highest difficulty."""
    df = pd.DataFrame(
        [
            _pr("alice", 1, "Good First Issue", 0),
            _pr("alice", 1, "Beginner", 0),  # same PR, second linked issue -> highest wins
            _pr("alice", 2, "Intermediate", 5),
        ]
    )

    progression = compute_progression_stats(df)

    row = progression.loc["alice"]
    assert row["pr_count"] == 2  # two distinct PRs, not three rows
    assert row["max_level"] == "Intermediate"
    assert row["start_level"] == "Beginner"  # PR 1's highest level, not Unknown


def test_start_level_skips_unknown():
    """A contributor's start level is the first *known* level, never Unknown."""
    df = pd.DataFrame([_pr("bob", 1, "Unknown", 0), _pr("bob", 2, "Good First Issue", 1)])
    assert compute_progression_stats(df).loc["bob"]["start_level"] == "Good First Issue"


def test_transitions_only_count_forward_progress():
    """Transitions record forward jumps in max level; regressions/repeats do not."""
    df = pd.DataFrame(
        [
            _pr("alice", 1, "Good First Issue", 0),
            _pr("alice", 2, "Beginner", 1),  # GFI -> Beginner
            _pr("alice", 3, "Good First Issue", 2),  # regression, ignored
            _pr("alice", 4, "Advanced", 3),  # Beginner -> Advanced
        ]
    )

    transitions = compute_transition_metrics(df)

    pairs = {(r["from"], r["to"]) for _, r in transitions.iterrows()}
    assert pairs == {("Good First Issue", "Beginner"), ("Beginner", "Advanced")}


def test_no_transitions_returns_empty_typed_frame():
    """A single-level contributor produces no transitions but a well-typed frame."""
    df = pd.DataFrame([_pr("solo", 1, "Beginner", 0)])
    result = compute_transition_metrics(df)
    assert result.empty
    assert list(result.columns) == ["from", "to", "count"]
