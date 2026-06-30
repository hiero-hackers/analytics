"""Tests for maintainer-pipeline aggregations."""

from datetime import UTC, datetime
from unittest.mock import patch

import pandas as pd

from hiero_analytics.analysis.maintainer_pipeline import (
    _active_window_for_year,
    activity_to_role_dataframe,
    build_maintainer_repo_pipeline,
    build_maintainer_yearly_pipeline,
    collapse_repo_pipeline_tail,
)
from hiero_analytics.data_sources.models import ContributorActivityRecord


def _record(
    activity_type: str,
    actor: str,
    repo: str,
    year: int,
    target_type: str = "pull_request",
    month: int = 1,
) -> ContributorActivityRecord:
    """Create a synthetic ContributorActivityRecord at the given year/month."""
    return ContributorActivityRecord(
        repo=repo,
        activity_type=activity_type,
        actor=actor,
        occurred_at=datetime(year, month, 1, tzinfo=UTC),
        target_type=target_type,
        target_number=1,
    )


def _h2_record(
    activity_type: str,
    actor: str,
    repo: str,
    year: int,
) -> ContributorActivityRecord:
    """Shorthand for a record placed in H2 (July) of the given year."""
    return _record(activity_type, actor, repo, year, month=7)


def test_activity_to_role_dataframe_filters_unknown_types():
    """Only maintainer activity records should be classified into governance stages."""
    role_lookup = {"repo-a": {"alice": "maintainer", "bob": "triage", "dana": "committer"}}
    records = [
        _record("authored_issue", "dana", "org/repo-a", 2024, target_type="issue"),
        _record("authored_pull_request", "alice", "org/repo-a", 2024),
        _record("reviewed_pull_request", "bob", "org/repo-a", 2024),
        _record("merged_pull_request", "carol", "org/repo-a", 2024),
        _record("ignored_event", "dave", "org/repo-a", 2024),
    ]

    df = activity_to_role_dataframe(records, role_lookup)

    assert len(df) == 4
    assert set(df["repo"]) == {"repo-a"}
    # alice -> maintainer, bob -> triage, dana -> committer, carol has no entry -> general_user
    assert set(df["stage"]) == {"maintainer", "triage", "committer", "general_user"}


def test_activity_to_role_dataframe_defaults_unknown_actor_to_general_user():
    """Actors missing from the lookup should remain in the general-user stage."""
    records = [_record("authored_pull_request", "unknown_actor", "org/repo-a", 2024)]
    df = activity_to_role_dataframe(records, {})
    assert df.iloc[0]["stage"] == "general_user"


def test_activity_to_role_dataframe_matches_actor_case_insensitively():
    """Mixed-case GitHub logins should still match normalized governance roles."""
    records = [_record("authored_pull_request", "Alice", "org/repo-a", 2024)]

    df = activity_to_role_dataframe(records, {"repo-a": {"alice": "maintainer"}})

    assert df.iloc[0]["stage"] == "maintainer"


def test_build_maintainer_yearly_pipeline_counts_unique_actors_per_stage():
    """Yearly rollups should count unique actors once per stage."""
    role_lookup = {
        "repo-a": {"alice": "general_user", "bob": "triage", "carol": "committer", "dana": "maintainer"}
    }
    # Use H2 events so they fall inside the completed-year activity window.
    records = [
        _record("authored_issue", "dana", "org/repo-a", 2024, target_type="issue", month=7),
        _h2_record("authored_pull_request", "alice", "org/repo-a", 2024),
        _h2_record("authored_pull_request", "alice", "org/repo-a", 2024),
        _h2_record("reviewed_pull_request", "bob", "org/repo-a", 2024),
        _h2_record("merged_pull_request", "carol", "org/repo-a", 2024),
    ]

    stage_df = activity_to_role_dataframe(records, role_lookup)
    yearly = build_maintainer_yearly_pipeline(stage_df)

    row = yearly.iloc[0]
    assert row["year"] == 2024
    assert row["general_user"] == 1
    assert row["triage"] == 1
    assert row["committer"] == 1
    assert row["maintainer"] == 1


def test_build_maintainer_repo_pipeline_sorts_by_total():
    """Repo rollups should sort repositories by total active contributors."""
    now = datetime.now(UTC)
    role_lookup = {
        "repo-a": {"alice": "general_user", "bob": "triage", "carol": "committer"},
        "repo-b": {"dana": "general_user"},
    }
    # Use recent records so they fall within the active window.
    recent_year = now.year
    recent_month = now.month
    records = [
        _record("authored_pull_request", "alice", "org/repo-a", recent_year, month=recent_month),
        _record("reviewed_pull_request", "bob", "org/repo-a", recent_year, month=recent_month),
        _record("merged_pull_request", "carol", "org/repo-a", recent_year, month=recent_month),
        _record("authored_pull_request", "dana", "org/repo-b", recent_year, month=recent_month),
    ]

    stage_df = activity_to_role_dataframe(records, role_lookup)
    by_repo = build_maintainer_repo_pipeline(stage_df)

    assert by_repo.iloc[0]["repo"] == "repo-a"
    assert by_repo.iloc[0]["general_user"] == 1
    assert by_repo.iloc[0]["triage"] == 1
    assert by_repo.iloc[0]["committer"] == 1


def test_build_maintainer_repo_pipeline_excludes_inactive():
    """Contributors with no activity in the trailing window should not appear."""
    role_lookup = {"repo-a": {}}
    # Place the record in 2020 — well outside any 183-day trailing window.
    records = [_record("authored_pull_request", "alice", "org/repo-a", 2020)]

    stage_df = activity_to_role_dataframe(records, role_lookup)
    by_repo = build_maintainer_repo_pipeline(stage_df)

    assert by_repo.empty


# ---------------------------------------------------------------------------
# _active_window_for_year
# ---------------------------------------------------------------------------


def test_active_window_for_completed_year_is_fixed_h2():
    """Completed years should use a fixed July-1 to Dec-31 window."""
    today = datetime(2026, 4, 24, tzinfo=UTC)
    start, end = _active_window_for_year(2025, today)

    assert start == datetime(2025, 7, 1, tzinfo=UTC)
    assert end == datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC)


def test_active_window_for_current_year_is_trailing_183_days():
    """The current (incomplete) year should use a trailing 183-day window."""
    today = datetime(2026, 4, 24, tzinfo=UTC)
    start, end = _active_window_for_year(2026, today)

    assert end == today
    assert (end - start).days == 183


# ---------------------------------------------------------------------------
# build_maintainer_yearly_pipeline – activity-window filtering
# ---------------------------------------------------------------------------


def test_yearly_pipeline_excludes_h1_events_for_completed_year():
    """H1 events (Jan–Jun) in a completed year should not be counted."""
    role_lookup = {"repo-a": {}}
    records = [
        _record("authored_pull_request", "alice", "org/repo-a", 2024, month=3),  # H1 – excluded
        _h2_record("authored_pull_request", "bob", "org/repo-a", 2024),           # H2 – included
    ]

    stage_df = activity_to_role_dataframe(records, role_lookup)
    yearly = build_maintainer_yearly_pipeline(stage_df)

    row = yearly[yearly["year"] == 2024].iloc[0]
    # Only bob's H2 event should be counted.
    assert row["general_user"] == 1


def test_yearly_pipeline_historical_bars_are_stable():
    """Re-running the pipeline at a later date must not change completed-year counts."""
    role_lookup = {"repo-a": {}}
    records = [_h2_record("authored_pull_request", "alice", "org/repo-a", 2025)]
    stage_df = activity_to_role_dataframe(records, role_lookup)

    # Simulate pipeline run in April 2026.
    today_apr_2026 = datetime(2026, 4, 24, tzinfo=UTC)
    # Simulate pipeline run in October 2026.
    today_oct_2026 = datetime(2026, 10, 1, tzinfo=UTC)

    with patch("hiero_analytics.analysis.maintainer_pipeline.datetime") as mock_dt:
        mock_dt.now.return_value = today_apr_2026
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        yearly_apr = build_maintainer_yearly_pipeline(stage_df)

    with patch("hiero_analytics.analysis.maintainer_pipeline.datetime") as mock_dt:
        mock_dt.now.return_value = today_oct_2026
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        yearly_oct = build_maintainer_yearly_pipeline(stage_df)

    count_apr = yearly_apr[yearly_apr["year"] == 2025]["general_user"].iloc[0]
    count_oct = yearly_oct[yearly_oct["year"] == 2025]["general_user"].iloc[0]
    assert count_apr == count_oct, "Historical 2025 count must not change between refreshes"


def test_collapse_repo_pipeline_tail_aggregates_remaining_rows():
    """Long repo tails should collapse into a single aggregated chart row."""
    repo_df = pd.DataFrame(
        [
            {"repo": "repo-a", "general_user": 10, "triage": 1, "committer": 2, "maintainer": 3},
            {"repo": "repo-b", "general_user": 8, "triage": 1, "committer": 2, "maintainer": 1},
            {"repo": "repo-c", "general_user": 6, "triage": 1, "committer": 1, "maintainer": 1},
            {"repo": "repo-d", "general_user": 4, "triage": 0, "committer": 1, "maintainer": 1},
        ]
    )

    collapsed = collapse_repo_pipeline_tail(repo_df, max_repos=3)

    assert len(collapsed) == 3
    assert collapsed.iloc[0]["repo"] == "repo-a"
    assert collapsed.iloc[1]["repo"] == "repo-b"
    assert collapsed.iloc[2]["repo"] == "Other Repos (2)"
    assert collapsed.iloc[2]["general_user"] == 10
    assert collapsed.iloc[2]["triage"] == 1
    assert collapsed.iloc[2]["committer"] == 2
    assert collapsed.iloc[2]["maintainer"] == 2


def test_collapse_repo_pipeline_tail_noop_when_below_limit():
    """Short repo tables should remain unchanged when under the chart limit."""
    repo_df = pd.DataFrame(
        [
            {"repo": "repo-a", "general_user": 1, "triage": 0, "committer": 0, "maintainer": 0},
            {"repo": "repo-b", "general_user": 1, "triage": 0, "committer": 0, "maintainer": 0},
        ]
    )

    collapsed = collapse_repo_pipeline_tail(repo_df, max_repos=5)

    assert collapsed.equals(repo_df)
