"""Tests for maintainer-pipeline aggregations."""

from datetime import UTC, datetime
from unittest.mock import patch

import pandas as pd

from hiero_analytics.analysis.maintainer_pipeline import (
    activity_to_role_dataframe,
    build_maintainer_daily_pipeline,
    build_maintainer_monthly_pipeline,
    build_maintainer_repo_pipeline,
    build_maintainer_weekly_pipeline,
    build_maintainer_yearly_pipeline,
    calendar_recent_buckets,
    humanize_day_label,
    humanize_month_label,
    humanize_week_label,
    last_calendar_buckets,
)
from hiero_analytics.data_sources.models import ContributorActivityRecord


def _record(
    activity_type: str,
    actor: str,
    repo: str,
    year: int,
    target_type: str = "pull_request",
    month: int = 1,
    day: int = 1,
) -> ContributorActivityRecord:
    """Create a synthetic ContributorActivityRecord at the given year/month/day."""
    return ContributorActivityRecord(
        repo=repo,
        activity_type=activity_type,
        actor=actor,
        occurred_at=datetime(year, month, day, tzinfo=UTC),
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
# last_calendar_buckets / calendar_recent_buckets
# ---------------------------------------------------------------------------


def _month_pipeline(n: int) -> pd.DataFrame:
    """Build a chronologically-sorted monthly pipeline table with ``n`` rows."""
    rows = [
        {"month": f"2024-{m:02d}", "general_user": m, "triage": 0, "committer": 0, "maintainer": 0}
        for m in range(1, n + 1)
    ]
    return pd.DataFrame(rows)


def test_last_calendar_buckets_daily_weekly_monthly():
    """Labels are complete calendar spans ending at now's bucket, oldest first."""
    now = datetime(2024, 12, 15, 12, 0, tzinfo=UTC)  # a Sunday; ISO week 50

    assert last_calendar_buckets(now, 3, "day") == ["2024-12-13", "2024-12-14", "2024-12-15"]
    assert last_calendar_buckets(now, 3, "week") == ["2024-W48", "2024-W49", "2024-W50"]
    assert last_calendar_buckets(now, 3, "month") == ["2024-10", "2024-11", "2024-12"]


def test_last_calendar_buckets_cross_boundaries():
    """Month walking crosses the year boundary; weeks cross ISO years."""
    now = datetime(2025, 1, 2, tzinfo=UTC)  # ISO week 2025-W01

    assert last_calendar_buckets(now, 3, "month") == ["2024-11", "2024-12", "2025-01"]
    assert last_calendar_buckets(now, 2, "week") == ["2024-W52", "2025-W01"]


def test_calendar_recent_buckets_windows_by_calendar_not_by_populated_rows():
    """A sparse table must not stretch older activity into the window (#coderabbit).

    Only 2024-03 and 2024-12 have activity; a 3-month window ending December
    contains October and November as zero rows and excludes March entirely.
    """
    pipeline = pd.DataFrame(
        [
            {"month": "2024-03", "general_user": 7, "triage": 0, "committer": 0, "maintainer": 1},
            {"month": "2024-12", "general_user": 2, "triage": 0, "committer": 0, "maintainer": 0},
        ]
    )

    windowed = calendar_recent_buckets(pipeline, ["2024-10", "2024-11", "2024-12"])

    assert list(windowed["month"]) == ["2024-10", "2024-11", "2024-12"]
    assert list(windowed["general_user"]) == [0, 0, 2]
    assert "2024-03" not in set(windowed["month"])
    assert windowed["maintainer"].dtype.kind == "i"  # zero-fill keeps integer counts


def test_calendar_recent_buckets_empty_input_stays_empty():
    """An empty pipeline stays empty so the plotting layer still skips the chart."""
    pipeline = pd.DataFrame(columns=["month", "general_user", "triage", "committer", "maintainer"])

    assert calendar_recent_buckets(pipeline, ["2024-11", "2024-12"]).empty


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


def test_daily_pipeline_buckets_by_calendar_day():
    """The finest resolution: same whole-bucket rule, one bar per day."""
    role_lookup = {"repo-a": {}}
    records = [
        _record("authored_pull_request", "alice", "org/repo-a", 2026, month=3, day=4),
        _record("reviewed_pull_request", "bob", "org/repo-a", 2026, month=3, day=4),
        _record("authored_pull_request", "alice", "org/repo-a", 2026, month=3, day=5),
    ]
    stage_df = activity_to_role_dataframe(records, role_lookup)

    daily = build_maintainer_daily_pipeline(stage_df)

    assert list(daily["day"]) == ["2026-03-04", "2026-03-05"]
    assert list(daily["general_user"]) == [2, 1]


def test_every_time_view_agrees_on_one_day_of_activity():
    """The four resolutions are one rule zoomed — they cannot disagree on a single day."""
    role_lookup = {"repo-a": {}}
    records = [
        _record("authored_pull_request", "alice", "org/repo-a", 2026, month=3, day=4),
        _record("reviewed_pull_request", "bob", "org/repo-a", 2026, month=3, day=4),
    ]
    stage_df = activity_to_role_dataframe(records, role_lookup)

    counts = {
        "day": build_maintainer_daily_pipeline(stage_df)["general_user"].iloc[0],
        "week": build_maintainer_weekly_pipeline(stage_df)["general_user"].iloc[0],
        "month": build_maintainer_monthly_pipeline(stage_df)["general_user"].iloc[0],
        "year": build_maintainer_yearly_pipeline(stage_df)["general_user"].iloc[0],
    }

    assert set(counts.values()) == {2}, counts


def test_bucket_labels_humanize_for_charts_and_degrade_raw():
    """Charts speak human ('w/c 3 Aug'), CSVs keep sortable keys; junk passes through."""
    assert humanize_month_label("2026-07") == "Jul 2026"
    assert humanize_week_label("2026-W32") == "w/c 3 Aug 2026"
    assert humanize_day_label("2026-08-05") == "Wed 5 Aug 2026"
    assert humanize_week_label("not-a-week") == "not-a-week"
