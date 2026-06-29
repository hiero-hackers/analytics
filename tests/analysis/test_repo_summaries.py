"""Tests for per-repository rollups derived from role_coverage_all."""

from __future__ import annotations

import pandas as pd

from hiero_analytics.analysis.repo_summaries import (
    build_repo_activity_overview,
    build_review_load_share,
    find_understaffed_repos,
)


def test_repo_activity_overview_rolls_up_by_role():
    """Per-repo rollup: holder counts by role, recent actions per role, sorted by recent."""
    coverage_all = pd.DataFrame(
        [
            # repo A: a busy maintainer + a quiet committer
            {"repo": "o/a", "granted_role": "maintainer", "status": "active", "total_actions": 50,
             "prs_recent": 3, "reviews_recent": 5, "merges_recent": 2, "issues_recent": 0, "labels_recent": 0,
             "last_active": "2026-06-20"},
            {"repo": "o/a", "granted_role": "committer", "status": "quiet", "total_actions": 4,
             "prs_recent": 0, "reviews_recent": 0, "merges_recent": 0, "issues_recent": 0, "labels_recent": 0,
             "last_active": "2026-01-01"},
            # repo B: one triage holder, lightly active
            {"repo": "o/b", "granted_role": "triage", "status": "active", "total_actions": 2,
             "prs_recent": 1, "reviews_recent": 0, "merges_recent": 0, "issues_recent": 0, "labels_recent": 0,
             "last_active": "2026-06-10"},
        ]
    )
    overview = build_repo_activity_overview(coverage_all)

    assert list(overview["repo"]) == ["o/a", "o/b"]  # o/a is more active recently -> first
    a = overview[overview["repo"] == "o/a"].iloc[0]
    assert a["maintainers"] == 1 and a["committers"] == 1 and a["triage"] == 0
    assert a["active_recent"] == 1  # only the maintainer is active
    assert a["maintainer_actions_recent"] == 10  # 3+5+2
    assert a["committer_actions_recent"] == 0
    assert a["actions_recent"] == 10
    assert a["actions_all_time"] == 54  # 50 + 4


def test_repo_activity_overview_empty():
    """An empty coverage table yields an empty overview with the right columns."""
    out = build_repo_activity_overview(pd.DataFrame())
    assert out.empty
    assert "actions_recent" in out.columns


def test_find_understaffed_repos_flags_low_maintainer_repos():
    """Repos with <=1 active maintainer are flagged, with committer/triage counts."""
    coverage = pd.DataFrame(
        [
            # repo a: 1 maintainer (quiet) + 2 committers -> flagged
            {"repo": "o/a", "user": "m1", "granted_role": "maintainer", "status": "quiet"},
            {"repo": "o/a", "user": "c1", "granted_role": "committer", "status": "active"},
            {"repo": "o/a", "user": "c2", "granted_role": "committer", "status": "active"},
            # repo b: 3 maintainers -> not flagged
            {"repo": "o/b", "user": "m1", "granted_role": "maintainer", "status": "active"},
            {"repo": "o/b", "user": "m2", "granted_role": "maintainer", "status": "active"},
            {"repo": "o/b", "user": "m3", "granted_role": "maintainer", "status": "active"},
            # repo c: 0 maintainers, only triage -> flagged (worst)
            {"repo": "o/c", "user": "t1", "granted_role": "triage", "status": "active"},
        ]
    )
    out = find_understaffed_repos(coverage, max_active_maintainers=1)
    assert set(out["repo"]) == {"a", "c"}  # b has 3 active maintainers
    assert list(out["repo"])[0] == "c"  # 0 maintainers sorts first (fewest active, then total)
    a = out[out["repo"] == "a"].iloc[0]
    assert a["maintainers"] == 1 and a["active_maintainers"] == 0 and a["committers"] == 2


def test_review_load_share_includes_committers_and_computes_concentration():
    """Committers count too (they can merge); triage is excluded; tiny repos dropped."""

    def row(repo, user, role, reviews, merges):
        return {
            "repo": repo, "user": user, "granted_role": role, "status": "active",
            "reviews_recent": reviews, "merges_recent": merges,
        }

    coverage = pd.DataFrame(
        [
            # repo a: a committer carries most of the load; a maintainer does the rest
            row("o/a", "carol-committer", "committer", 70, 10),  # 80
            row("o/a", "mona-maintainer", "maintainer", 15, 5),  # 20
            row("o/a", "tom-triage", "triage", 50, 0),  # triage can't merge -> excluded
            # repo b: only 5 total -> below min_actions, dropped
            row("o/b", "x", "maintainer", 3, 2),
        ]
    )
    out = build_review_load_share(coverage, min_actions=20)
    assert list(out["repo"]) == ["a"]  # b dropped; triage didn't inflate a
    a = out.iloc[0]
    assert a["top_carrier"] == "carol-committer"  # the committer, not the maintainer
    assert a["top_role"] == "committer"
    assert a["load_recent"] == 100  # 80 + 20, triage's 50 excluded
    assert a["top_share"] == 0.8
    assert a["mergers"] == 2


def test_review_load_share_empty():
    """No review+merge load yields an empty frame with the right columns."""
    out = build_review_load_share(pd.DataFrame())
    assert out.empty and "top_role" in out.columns
