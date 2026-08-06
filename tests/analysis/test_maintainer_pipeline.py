"""Tests for maintainer-pipeline aggregations."""

from datetime import UTC, datetime
from unittest.mock import patch

import pandas as pd

from hiero_analytics.analysis.maintainer_pipeline import (
    _active_window_for_year,
    activity_to_role_dataframe,
    build_maintainer_monthly_pipeline,
    build_maintainer_repo_pipeline,
    build_maintainer_weekly_pipeline,
    build_maintainer_yearly_h2_pipeline,
    build_maintainer_yearly_pipeline,
    recent_buckets,
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


def test_activity_to_role_dataframe_excludes_bots():
    """Automation accounts aren't people and must be dropped from the pipeline."""
    records = [
        _record("authored_pull_request", "alice", "org/repo-a", 2024),
        _record("authored_pull_request", "dependabot[bot]", "org/repo-a", 2024),
        _record("merged_pull_request", "dependabot", "org/repo-a", 2024),
        _record("reviewed_pull_request", "some-bot", "org/repo-a", 2024),
        _record("authored_issue", "github-actions", "org/repo-a", 2024, target_type="issue"),
    ]

    df = activity_to_role_dataframe(records, {})

    assert list(df["actor"]) == ["alice"]


def test_build_maintainer_yearly_pipeline_counts_unique_actors_per_stage():
    """Yearly rollups should count unique actors once per stage."""
    role_lookup = {"repo-a": {"alice": "general_user", "bob": "triage", "carol": "committer", "dana": "maintainer"}}
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


def test_build_maintainer_yearly_pipeline_counts_each_person_once_by_highest_role():
    """A person with different roles in different repos counts once, in their highest band."""
    role_lookup = {
        "repo-a": {"alice": "maintainer"},
        "repo-b": {"alice": "general_user"},
    }
    records = [
        _h2_record("authored_pull_request", "alice", "org/repo-a", 2024),  # maintainer here
        _h2_record("reviewed_pull_request", "alice", "org/repo-b", 2024),  # general here
    ]

    stage_df = activity_to_role_dataframe(records, role_lookup)
    yearly = build_maintainer_yearly_pipeline(stage_df)

    row = yearly.iloc[0]
    assert row["maintainer"] == 1  # counted under her highest role only
    assert row["general_user"] == 0  # not double-counted in the lower band
    assert row["committer"] == 0
    assert row["triage"] == 0


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
# build_maintainer_yearly_h2_pipeline – end-of-year activity window
# ---------------------------------------------------------------------------


def test_yearly_h2_pipeline_excludes_h1_events_for_completed_year():
    """H1 events (Jan–Jun) in a completed year should not be counted."""
    role_lookup = {"repo-a": {}}
    records = [
        _record("authored_pull_request", "alice", "org/repo-a", 2024, month=3),  # H1 – excluded
        _h2_record("authored_pull_request", "bob", "org/repo-a", 2024),  # H2 – included
    ]

    stage_df = activity_to_role_dataframe(records, role_lookup)
    yearly = build_maintainer_yearly_h2_pipeline(stage_df)

    row = yearly[yearly["year"] == 2024].iloc[0]
    # Only bob's H2 event should be counted.
    assert row["general_user"] == 1


def test_yearly_h2_pipeline_historical_bars_are_stable():
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
        mock_dt.side_effect = datetime
        yearly_apr = build_maintainer_yearly_h2_pipeline(stage_df)

    with patch("hiero_analytics.analysis.maintainer_pipeline.datetime") as mock_dt:
        mock_dt.now.return_value = today_oct_2026
        mock_dt.side_effect = datetime
        yearly_oct = build_maintainer_yearly_h2_pipeline(stage_df)

    count_apr = yearly_apr[yearly_apr["year"] == 2025]["general_user"].iloc[0]
    count_oct = yearly_oct[yearly_oct["year"] == 2025]["general_user"].iloc[0]
    assert count_apr == count_oct, "Historical 2025 count must not change between refreshes"


def test_yearly_h2_pipeline_current_bar_uses_full_trailing_window():
    """Early in a year the current bar's trailing window reaches into last December, as its note says."""
    role_lookup = {"repo-a": {}}
    records = [
        _record("authored_pull_request", "december-dev", "org/repo-a", 2025, month=12),
        _record("authored_pull_request", "january-dev", "org/repo-a", 2026, month=1),
    ]
    stage_df = activity_to_role_dataframe(records, role_lookup)

    today_feb_2026 = datetime(2026, 2, 15, tzinfo=UTC)
    with patch("hiero_analytics.analysis.maintainer_pipeline.datetime") as mock_dt:
        mock_dt.now.return_value = today_feb_2026
        mock_dt.side_effect = datetime
        yearly = build_maintainer_yearly_h2_pipeline(stage_df)

    current = yearly[yearly["year"] == 2026].iloc[0]
    assert current["general_user"] == 2  # window spans Dec 2025 + Jan 2026, not year-to-date
    past = yearly[yearly["year"] == 2025].iloc[0]
    assert past["general_user"] == 1  # the Dec event still counts in 2025's fixed H2 bar


# ---------------------------------------------------------------------------
# build_maintainer_monthly_pipeline
# ---------------------------------------------------------------------------


def test_monthly_pipeline_counts_unique_actors():
    """Monthly rollups should count unique actors once per month by highest role."""
    now = datetime.now(UTC)
    role_lookup = {"repo-a": {"alice": "maintainer", "bob": "general_user"}}
    records = [
        _record("authored_pull_request", "alice", "org/repo-a", now.year, month=now.month),
        _record("reviewed_pull_request", "alice", "org/repo-a", now.year, month=now.month),
        _record("authored_pull_request", "bob", "org/repo-a", now.year, month=now.month),
    ]

    stage_df = activity_to_role_dataframe(records, role_lookup)
    monthly = build_maintainer_monthly_pipeline(stage_df)

    assert len(monthly) >= 1
    row = monthly.iloc[-1]  # most recent month
    assert row["maintainer"] == 1
    assert row["general_user"] == 1


def test_monthly_pipeline_empty_input():
    """Empty input should produce an empty DataFrame with correct columns."""
    stage_df = pd.DataFrame(columns=["repo", "actor", "occurred_at", "year", "stage"])
    monthly = build_maintainer_monthly_pipeline(stage_df)

    assert list(monthly.columns) == ["month", "general_user", "triage", "committer", "maintainer"]
    assert monthly.empty


def test_monthly_pipeline_multiple_months():
    """Records in different months should produce separate rows."""
    role_lookup = {"repo-a": {}}
    records = [
        _record("authored_pull_request", "alice", "org/repo-a", 2024, month=7),
        _record("authored_pull_request", "bob", "org/repo-a", 2024, month=8),
    ]

    stage_df = activity_to_role_dataframe(records, role_lookup)
    monthly = build_maintainer_monthly_pipeline(stage_df)

    assert len(monthly) == 2
    assert "2024-07" in monthly["month"].values
    assert "2024-08" in monthly["month"].values


def test_monthly_pipeline_current_month_is_month_to_date_not_trailing():
    """The current month is counted month-to-date, not as a 6-month trailing window.

    Activity from earlier periods must land in its own bucket and never leak into
    the current month's count.
    """
    now = datetime.now(UTC)
    role_lookup = {"repo-a": {}}
    records = [
        _record("authored_pull_request", "current_person", "org/repo-a", now.year, month=now.month),
        _record("authored_pull_request", "old_person", "org/repo-a", 2020, month=1),
    ]

    stage_df = activity_to_role_dataframe(records, role_lookup)
    monthly = build_maintainer_monthly_pipeline(stage_df)

    current_label = f"{now.year:04d}-{now.month:02d}"
    current_row = monthly[monthly["month"] == current_label].iloc[0]

    assert current_row["general_user"] == 1  # only the current-month contributor
    assert "2020-01" in monthly["month"].values  # older activity stays in its own bucket


# ---------------------------------------------------------------------------
# build_maintainer_weekly_pipeline
# ---------------------------------------------------------------------------


def test_weekly_pipeline_counts_unique_actors():
    """Weekly rollups should count unique actors once per week by highest role."""
    now = datetime.now(UTC)
    role_lookup = {"repo-a": {"alice": "committer", "bob": "general_user"}}
    records = [
        _record("authored_pull_request", "alice", "org/repo-a", now.year, month=now.month),
        _record("authored_pull_request", "bob", "org/repo-a", now.year, month=now.month),
    ]

    stage_df = activity_to_role_dataframe(records, role_lookup)
    weekly = build_maintainer_weekly_pipeline(stage_df)

    assert len(weekly) >= 1
    row = weekly.iloc[-1]
    assert row["committer"] == 1
    assert row["general_user"] == 1


def test_weekly_pipeline_empty_input():
    """Empty input should produce an empty DataFrame with correct columns."""
    stage_df = pd.DataFrame(columns=["repo", "actor", "occurred_at", "year", "stage"])
    weekly = build_maintainer_weekly_pipeline(stage_df)

    assert list(weekly.columns) == ["week", "general_user", "triage", "committer", "maintainer"]
    assert weekly.empty


def test_weekly_pipeline_iso_week_labels():
    """Week labels should follow ISO-week format YYYY-Www."""
    role_lookup = {"repo-a": {}}
    # 2024-07-01 is a Monday (2024-W27)
    records = [
        _record("authored_pull_request", "alice", "org/repo-a", 2024, month=7),
    ]

    stage_df = activity_to_role_dataframe(records, role_lookup)
    weekly = build_maintainer_weekly_pipeline(stage_df)

    assert len(weekly) >= 1
    # ISO week label for July 1 2024 (Monday) is 2024-W27
    assert weekly.iloc[0]["week"] == "2024-W27"


def test_weekly_pipeline_counts_each_week_separately():
    """Weekly counts are strictly per-week — one week's activity never leaks into another."""
    role_lookup = {"repo-a": {}}
    records = [
        _record("authored_pull_request", "alice", "org/repo-a", 2024, month=7),  # 2024-W27
        _record("authored_pull_request", "bob", "org/repo-a", 2020, month=1),  # 2020-W01
    ]

    stage_df = activity_to_role_dataframe(records, role_lookup)
    weekly = build_maintainer_weekly_pipeline(stage_df)

    assert len(weekly) == 2
    assert set(weekly["general_user"]) == {1}  # each week has only its own contributor
    assert "2024-W27" in weekly["week"].values
    assert "2020-W01" in weekly["week"].values


# ---------------------------------------------------------------------------
# recent_buckets
# ---------------------------------------------------------------------------


def _month_pipeline(n: int) -> pd.DataFrame:
    """Build a chronologically-sorted monthly pipeline table with ``n`` rows."""
    rows = [
        {"month": f"2024-{m:02d}", "general_user": m, "triage": 0, "committer": 0, "maintainer": 0}
        for m in range(1, n + 1)
    ]
    return pd.DataFrame(rows)


def test_recent_buckets_keeps_only_most_recent():
    """recent_buckets should return the tail (newest) rows in chronological order."""
    pipeline = _month_pipeline(12)

    trimmed = recent_buckets(pipeline, 3)

    assert list(trimmed["month"]) == ["2024-10", "2024-11", "2024-12"]
    assert list(trimmed.index) == [0, 1, 2]  # index reset


def test_recent_buckets_newest_first_reverses_order():
    """newest_first should return the most recent buckets in reverse-chronological order."""
    pipeline = _month_pipeline(12)

    trimmed = recent_buckets(pipeline, 3, newest_first=True)

    assert list(trimmed["month"]) == ["2024-12", "2024-11", "2024-10"]
    assert list(trimmed.index) == [0, 1, 2]  # index reset


def test_recent_buckets_noop_when_within_limit():
    """A table already within the limit should be returned unchanged."""
    pipeline = _month_pipeline(3)

    trimmed = recent_buckets(pipeline, 24)

    assert trimmed.equals(pipeline)


def test_recent_buckets_empty_input():
    """Empty input should be returned as-is."""
    pipeline = pd.DataFrame(columns=["month", "general_user", "triage", "committer", "maintainer"])

    trimmed = recent_buckets(pipeline, 24)

    assert trimmed.empty


def test_recent_buckets_non_positive_limit_is_noop():
    """A non-positive limit should not trim the table."""
    pipeline = _month_pipeline(5)

    assert recent_buckets(pipeline, 0).equals(pipeline)


# ---------------------------------------------------------------------------
# build_maintainer_yearly_pipeline – whole calendar year (#335)
# ---------------------------------------------------------------------------


def test_yearly_pipeline_counts_activity_anywhere_in_the_year():
    """The regression this fixes: an H1-only contributor was invisible yearly.

    They appeared in every monthly bar and no yearly bar, so the tabs beside
    each other answered different questions under the same name.
    """
    role_lookup = {"repo-a": {}}
    records = [
        _record("authored_pull_request", "spring-only", "org/repo-a", 2024, month=3),
        _h2_record("authored_pull_request", "autumn-only", "org/repo-a", 2024),
    ]

    stage_df = activity_to_role_dataframe(records, role_lookup)
    yearly = build_maintainer_yearly_pipeline(stage_df)

    assert yearly[yearly["year"] == 2024].iloc[0]["general_user"] == 2


def test_yearly_pipeline_agrees_with_the_monthly_view_on_who_was_active():
    """Yearly is the monthly rule at a coarser bucket — the tabs must not disagree."""
    role_lookup = {"repo-a": {}}
    records = [
        _record("authored_pull_request", "alice", "org/repo-a", 2024, month=2),
        _record("authored_pull_request", "bob", "org/repo-a", 2024, month=9),
    ]
    stage_df = activity_to_role_dataframe(records, role_lookup)

    yearly = build_maintainer_yearly_pipeline(stage_df)
    monthly = build_maintainer_monthly_pipeline(stage_df)

    people_seen_monthly = int(monthly["general_user"].sum())  # one distinct person per month here
    assert yearly[yearly["year"] == 2024].iloc[0]["general_user"] == people_seen_monthly


def test_yearly_pipeline_bars_do_not_move_with_the_run_date():
    """Calendar-year counting has no recency window, so refreshes cannot shift history."""
    role_lookup = {"repo-a": {}}
    records = [_record("authored_pull_request", "alice", "org/repo-a", 2025, month=3)]
    stage_df = activity_to_role_dataframe(records, role_lookup)

    with patch("hiero_analytics.analysis.maintainer_pipeline.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 4, 24, tzinfo=UTC)
        mock_dt.side_effect = datetime
        april = build_maintainer_yearly_pipeline(stage_df)
    with patch("hiero_analytics.analysis.maintainer_pipeline.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 10, 1, tzinfo=UTC)
        mock_dt.side_effect = datetime
        october = build_maintainer_yearly_pipeline(stage_df)

    assert april.equals(october)


def test_yearly_h2_view_is_a_subset_of_the_plain_yearly_view():
    """The two variants must be comparable: 'still here' can never exceed 'showed up'."""
    role_lookup = {"repo-a": {}}
    records = [
        _record("authored_pull_request", "spring-only", "org/repo-a", 2024, month=3),
        _h2_record("authored_pull_request", "stayed", "org/repo-a", 2024),
    ]
    stage_df = activity_to_role_dataframe(records, role_lookup)

    whole = build_maintainer_yearly_pipeline(stage_df)
    year_end = build_maintainer_yearly_h2_pipeline(stage_df)

    assert year_end[year_end["year"] == 2024].iloc[0]["general_user"] == 1
    assert whole[whole["year"] == 2024].iloc[0]["general_user"] == 2
