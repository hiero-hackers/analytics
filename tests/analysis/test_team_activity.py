"""Tests for team-level activity rollups."""

from __future__ import annotations

from datetime import UTC, datetime

from hiero_analytics.analysis.contributor_activity_profile import (
    build_contributor_profiles,
    build_contributor_profiles_by_repo,
    latest_activity_by_account,
)
from hiero_analytics.analysis.team_activity import (
    build_team_activity_by_repo,
    build_team_activity_summary,
)
from hiero_analytics.data_sources.models import ContributorActivityRecord


def _ev(actor, activity_type, n, *, repo="o/x", target_author=None, month=1):
    target_type = "issue" if activity_type == "authored_issue" else "pull_request"
    return ContributorActivityRecord(
        repo=repo,
        activity_type=activity_type,
        actor=actor,
        occurred_at=datetime(2024, month, 1, tzinfo=UTC),
        target_type=target_type,
        target_number=n,
        target_author=target_author or actor,
    )


def test_team_summary_flags_dark_teams_and_aggregates():
    """Team status is dark when no member is active in the window; counts sum across members."""
    records = [
        _ev("alice", "authored_pull_request", 1, month=6),  # recent
        _ev("alice", "reviewed_pull_request", 2, target_author="x", month=6),
        _ev("stale", "authored_pull_request", 3, month=1),  # ~180 days before now
    ]
    org_profiles = build_contributor_profiles(records)
    last_seen = latest_activity_by_account(records)
    team_members = {
        "live-team": {"alice"},
        "dark-team": {"stale", "neverseen"},  # stale is old, neverseen has no activity
    }
    summary = build_team_activity_summary(
        team_members, org_profiles, last_seen, now=datetime(2024, 7, 1, tzinfo=UTC), dark_after_days=180
    ).set_index("team")

    assert summary.loc["live-team", "status"] == "active"
    assert summary.loc["live-team", "active_members"] == 1
    assert summary.loc["live-team", "prs_opened"] == 1
    assert summary.loc["live-team", "reviews_given"] == 1
    assert summary.loc["dark-team", "status"] == "quiet"
    assert summary.loc["dark-team", "members"] == 2
    assert summary.loc["dark-team", "active_members"] == 0
    # the quiet team sorts before the active one
    assert summary.index[0] == "dark-team"


def test_team_by_repo_shows_where_a_team_is_active():
    """A team only appears for repos where its members have activity."""
    records = [
        _ev("alice", "authored_pull_request", 1, repo="o/x"),
        _ev("bob", "reviewed_pull_request", 2, repo="o/y", target_author="alice"),
    ]
    by_repo = build_contributor_profiles_by_repo(records)
    team_members = {"team-ab": {"alice", "bob"}, "team-ghost": {"nobody"}}

    table = build_team_activity_by_repo(team_members, by_repo)

    team_ab = table[table["team"] == "team-ab"]
    assert set(team_ab["repo"]) == {"o/x", "o/y"}  # active in both
    assert "team-ghost" not in set(table["team"])  # no activity -> absent

