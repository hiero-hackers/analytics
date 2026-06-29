"""Tests for role-coverage: governance roles joined to per-repo activity."""

from __future__ import annotations

from datetime import UTC, datetime

from hiero_analytics.analysis.contributor_activity_profile import (
    build_contributor_profiles,
    latest_activity_by_account,
)
from hiero_analytics.analysis.role_coverage import (
    annotate_repo_roles,
    build_repo_role_coverage,
    find_globally_quiet_role_holders,
    find_unbadged_role_work,
    looks_like_bot,
)
from hiero_analytics.data_sources.models import ContributorActivityRecord


def _ev(actor, activity_type, n, *, target_author=None, month=1):
    target_type = "issue" if activity_type == "authored_issue" else "pull_request"
    return ContributorActivityRecord(
        repo="o/repo",
        activity_type=activity_type,
        actor=actor,
        occurred_at=datetime(2024, month, 1, tzinfo=UTC),
        target_type=target_type,
        target_number=n,
        target_author=target_author or actor,
    )


def test_looks_like_bot():
    """Known bot names and common bot suffixes are detected; humans are not."""
    assert looks_like_bot("coderabbitai")
    assert looks_like_bot("dependabot[bot]")
    assert looks_like_bot("some-bot")
    assert not looks_like_bot("exploreriii")


def _seen(profiles):
    """All-time per-repo recency map derived from a profile table (for tests)."""
    return {str(r.contributor).lower(): r.last_active for r in profiles.itertuples()}


def test_quiet_when_no_activity_in_repo():
    """A role-holder with no activity in the repo is quiet, with null recency."""
    profiles = build_contributor_profiles([_ev("alice", "authored_pull_request", 1)])
    cov = build_repo_role_coverage(
        {"ghost": "maintainer"}, profiles, _seen(profiles), now=datetime(2024, 2, 1, tzinfo=UTC)
    )
    row = cov[cov["user"] == "ghost"].iloc[0]
    assert row["status"] == "quiet"
    assert row["last_active"] is None
    assert row["total_actions"] == 0


def test_quiet_when_last_active_beyond_window():
    """An active-but-stale holder (older than the window) is quiet."""
    profiles = build_contributor_profiles([_ev("m", "reviewed_pull_request", 1, target_author="x", month=1)])
    cov = build_repo_role_coverage(
        {"m": "maintainer"}, profiles, _seen(profiles), now=datetime(2024, 6, 1, tzinfo=UTC), active_within_days=90
    )
    assert cov[cov["user"] == "m"].iloc[0]["status"] == "quiet"  # ~150 days


def test_coverage_surfaces_raw_contribution_counts():
    """Coverage carries raw contribution counts (PRs/reviews/merges/issues/labels), no %."""
    records = [
        _ev("m", "authored_pull_request", 1),
        _ev("m", "reviewed_pull_request", 2, target_author="x"),
        _ev("m", "reviewed_pull_request", 3, target_author="y"),
        _ev("m", "merged_pull_request", 4, target_author="x"),
        _ev("m", "authored_issue", 5),
    ]
    profiles = build_contributor_profiles(records)
    cov = build_repo_role_coverage(
        {"m": "maintainer"}, profiles, _seen(profiles), now=datetime(2024, 1, 15, tzinfo=UTC)
    )
    row = cov.iloc[0]

    assert row["status"] == "active"
    assert row["prs_opened"] == 1
    assert row["reviews_given"] == 2
    assert row["merges_done"] == 1
    assert row["issues_opened"] == 1
    assert row["labels_applied"] == 0
    assert row["total_actions"] == 5  # 1 build + (2 reviews + 1 merge) + 1 issue
    assert "role_work_pct" not in cov.columns  # the derived % is gone


def test_coverage_reports_all_time_and_recent_counts():
    """All-time counts plus a windowed ``*_recent`` set when recent_profiles is given."""
    all_records = [
        _ev("m", "authored_pull_request", 1, month=1),
        _ev("m", "authored_pull_request", 2, month=1),
        _ev("m", "authored_pull_request", 3, month=6),  # the only recent one
    ]
    profiles = build_contributor_profiles(all_records)
    recent = build_contributor_profiles([all_records[2]])  # just the month-6 PR
    cov = build_repo_role_coverage(
        {"m": "maintainer"},
        profiles,
        _seen(profiles),
        now=datetime(2024, 6, 15, tzinfo=UTC),
        recent_profiles=recent,
    )
    row = cov.iloc[0]
    assert row["prs_opened"] == 3  # all-time
    assert row["prs_recent"] == 1  # last window only
    assert row["reviews_recent"] == 0


def test_recent_counts_zero_without_recent_profiles():
    """Omitting recent_profiles leaves the ``*_recent`` columns at zero."""
    profiles = build_contributor_profiles([_ev("m", "authored_pull_request", 1)])
    cov = build_repo_role_coverage(
        {"m": "maintainer"}, profiles, _seen(profiles), now=datetime(2024, 1, 15, tzinfo=UTC)
    )
    row = cov.iloc[0]
    assert row["prs_opened"] == 1
    assert row["prs_recent"] == 0


def test_quiet_holders_sort_before_active():
    """Quiet holders come first (most actionable)."""
    profiles = build_contributor_profiles([_ev("active1", "reviewed_pull_request", 1, target_author="x")])
    cov = build_repo_role_coverage(
        {"active1": "maintainer", "ghost": "triage"},
        profiles,
        _seen(profiles),
        now=datetime(2024, 1, 15, tzinfo=UTC),
    )
    assert list(cov["status"]) == ["quiet", "active"]


def test_unbadged_excludes_holders_and_bots():
    """Promotion candidates exclude role-holders and automation accounts."""
    records = [
        *[_ev("reviewer", "reviewed_pull_request", i, target_author="a") for i in range(25)],
        *[_ev("coderabbitai", "reviewed_pull_request", 100 + i, target_author="a") for i in range(30)],
        *[_ev("badged", "reviewed_pull_request", 200 + i, target_author="a") for i in range(25)],
    ]
    profiles = build_contributor_profiles(records)
    candidates = find_unbadged_role_work(
        profiles,
        {"badged": "maintainer"},
        now=datetime(2024, 1, 15, tzinfo=UTC),
        min_reviews=20,
    )
    assert list(candidates["user"]) == ["reviewer"]  # bot + holder excluded


def test_globally_quiet_flags_only_dark_everywhere():
    """Holders active anywhere are excluded; quiet-everywhere and never-active are flagged."""
    # alice: active recently (month 6). bob: last active month 1 (stale). ghost: never.
    last_seen = latest_activity_by_account(
        [
            _ev("alice", "reviewed_pull_request", 1, target_author="x", month=6),
            _ev("bob", "authored_pull_request", 2, month=1),
        ]
    )
    role_lookup = {
        "repoA": {"alice": "maintainer", "bob": "triage"},
        "repoB": {"alice": "committer", "bob": "committer", "ghost": "maintainer"},
    }
    quiet = find_globally_quiet_role_holders(
        role_lookup, last_seen, now=datetime(2024, 7, 1, tzinfo=UTC), threshold_days=180
    )

    assert set(quiet["user"]) == {"bob", "ghost"}  # alice active somewhere -> excluded
    bob = quiet[quiet["user"] == "bob"].iloc[0]
    assert bob["highest_role"] == "committer"  # committer > triage across repos
    assert bob["repos_held"] == 2
    # never-active 'ghost' sorts first (blank days), then bob
    assert quiet.iloc[0]["user"] == "ghost"
    assert bob["days_since_active"] == 182


def test_globally_quiet_empty_when_all_recently_active():
    """No quiet rows when every holder is active within the window."""
    last_seen = latest_activity_by_account([_ev("m", "reviewed_pull_request", 1, target_author="x", month=6)])
    quiet = find_globally_quiet_role_holders(
        {"r": {"m": "maintainer"}}, last_seen, now=datetime(2024, 6, 15, tzinfo=UTC), threshold_days=180
    )
    assert quiet.empty


def test_annotate_repo_roles_labels_role_per_repo():
    """Each (account, repo) row gets the account's role in that repo; else default."""
    import pandas as pd

    activity = pd.DataFrame(
        [
            {"repo": "o/x", "account": "Asha", "reviewing_and_guiding": 50},
            {"repo": "o/y", "account": "Asha", "reviewing_and_guiding": 3},
        ]
    )
    role_lookup = {"x": {"asha": "maintainer"}}  # role in x only; none in y

    out = annotate_repo_roles(activity, role_lookup)

    by_repo = out.set_index("repo")["repo_role"]
    assert by_repo["o/x"] == "maintainer"  # acting as maintainer here
    assert by_repo["o/y"] == "general"  # just a contributor here
    assert list(out.columns[:3]) == ["repo", "account", "repo_role"]
