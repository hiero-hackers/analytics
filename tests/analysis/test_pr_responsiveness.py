"""Time-to-first-review and time-to-merge, derived from the activity events."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from hiero_analytics.analysis.contributor_activity_profile import combined_activity_events
from hiero_analytics.analysis.pr_responsiveness import (
    MONTHLY_COLUMNS,
    PR_RESPONSE_COLUMNS,
    REPO_SUMMARY_COLUMNS,
    SUMMARY_COLUMNS,
    monthly_responsiveness,
    pr_response_times,
    responsiveness_summary,
)
from hiero_analytics.data_sources.models import ContributorActivityRecord

T0 = datetime(2026, 6, 1, 9, tzinfo=UTC)


def _event(repo, actor, activity_type, hours, number, target_author):
    return ContributorActivityRecord(
        repo=f"org/{repo}",
        activity_type=activity_type,
        actor=actor,
        occurred_at=T0 + timedelta(hours=hours),
        target_type="pull_request",
        target_number=number,
        target_author=target_author,
    )


def _opened(repo, author, number, at=0.0):
    return _event(repo, author, "authored_pull_request", at, number, author)


def _reviewed(repo, reviewer, author, number, at):
    return _event(repo, reviewer, "reviewed_pull_request", at, number, author)


def _merged(repo, merger, author, number, at):
    return _event(repo, merger, "merged_pull_request", at, number, author)


def _frame(*records) -> pd.DataFrame:
    return combined_activity_events(list(records))


def _one(frame: pd.DataFrame, number: int, repo: str = "org/sdk") -> pd.Series:
    selected = frame[(frame["repo"] == repo) & (frame["pr_number"] == number)]
    assert len(selected) == 1
    return selected.iloc[0]


def test_measures_the_wait_to_first_review_and_to_merge():
    """Each PR's waits are its first non-author review and its merge, in hours from creation."""
    prs = pr_response_times(
        _frame(
            _opened("sdk", "alice", 1, at=0),
            _reviewed("sdk", "bob", "alice", 1, at=5),
            _reviewed("sdk", "carol", "alice", 1, at=9),
            _merged("sdk", "bob", "alice", 1, at=30),
        )
    )

    row = _one(prs, 1)
    assert list(prs.columns) == PR_RESPONSE_COLUMNS
    assert row["author"] == "alice"
    assert row["hours_to_first_review"] == pytest.approx(5)
    assert row["hours_to_merge"] == pytest.approx(30)


def test_the_authors_own_review_activity_is_not_a_response():
    """An author replying in a review thread is a ``reviewed`` event, but not a wait ending."""
    prs = pr_response_times(
        _frame(
            _opened("sdk", "alice", 1, at=0),
            _reviewed("sdk", "alice", "alice", 1, at=1),
            _reviewed("sdk", "bob", "alice", 1, at=8),
            _merged("sdk", "bob", "alice", 1, at=10),
        )
    )

    assert _one(prs, 1)["hours_to_first_review"] == pytest.approx(8)


def test_a_review_after_the_merge_is_not_counted():
    """A review submitted after the merge is not a response the author waited for."""
    prs = pr_response_times(
        _frame(
            _opened("sdk", "alice", 1, at=0),
            _merged("sdk", "bob", "alice", 1, at=4),
            _reviewed("sdk", "carol", "alice", 1, at=20),
        )
    )

    row = _one(prs, 1)
    assert pd.isna(row["hours_to_first_review"])
    assert pd.isna(row["first_review_at"])
    assert row["hours_to_merge"] == pytest.approx(4)


def test_a_merged_pr_nobody_reviewed_still_has_a_merge_time():
    """With no other reviewer there is no first-review time, but the merge time stands."""
    prs = pr_response_times(_frame(_opened("sdk", "alice", 1), _merged("sdk", "alice", "alice", 1, at=2)))

    row = _one(prs, 1)
    assert pd.isna(row["hours_to_first_review"])
    assert row["hours_to_merge"] == pytest.approx(2)


def test_bots_and_unmerged_prs_are_out_of_the_population():
    """Only merged, human-authored, human-merged PRs with a recorded creation count."""
    prs = pr_response_times(
        _frame(
            # Bot-authored PR: never a contributor's wait.
            _opened("sdk", "dependabot[bot]", 1),
            _merged("sdk", "bob", "dependabot[bot]", 1, at=3),
            # Opened and reviewed but never merged (closed or still open).
            _opened("sdk", "alice", 2),
            _reviewed("sdk", "bob", "alice", 2, at=2),
            # Merge recorded without a recorded creation.
            _merged("sdk", "bob", "carol", 3, at=3),
            # Merged by a bot, so there is no merge event in the frame.
            _opened("sdk", "alice", 4),
            _merged("sdk", "mergify[bot]", "alice", 4, at=3),
            # The one that counts.
            _opened("sdk", "alice", 5),
            _merged("sdk", "bob", "alice", 5, at=6),
        )
    )

    assert prs["pr_number"].tolist() == [5]


def test_a_review_by_a_bot_is_not_a_response():
    """Automated reviews do not end a contributor's wait."""
    prs = pr_response_times(
        _frame(
            _opened("sdk", "alice", 1),
            _reviewed("sdk", "coderabbitai[bot]", "alice", 1, at=0.1),
            _reviewed("sdk", "bob", "alice", 1, at=12),
            _merged("sdk", "bob", "alice", 1, at=20),
        )
    )

    assert _one(prs, 1)["hours_to_first_review"] == pytest.approx(12)


def test_the_same_pr_in_two_repos_is_two_prs():
    """PR numbers repeat across repositories; the repository is part of the identity."""
    prs = pr_response_times(
        _frame(
            _opened("sdk", "alice", 1),
            _merged("sdk", "bob", "alice", 1, at=1),
            _opened("docs", "alice", 1),
            _merged("docs", "bob", "alice", 1, at=9),
        )
    )

    assert _one(prs, 1, "org/sdk")["hours_to_merge"] == pytest.approx(1)
    assert _one(prs, 1, "org/docs")["hours_to_merge"] == pytest.approx(9)


def test_a_duplicated_event_is_not_double_counted():
    """A repeated record collapses to one PR rather than inflating the counts."""
    prs = pr_response_times(
        _frame(
            _opened("sdk", "alice", 1),
            _opened("sdk", "alice", 1),
            _merged("sdk", "bob", "alice", 1, at=2),
            _merged("sdk", "bob", "alice", 1, at=2),
        )
    )

    assert len(prs) == 1


def test_a_merge_before_its_creation_is_dropped_as_a_data_error():
    """A negative wait is a data error, not a fast merge."""
    prs = pr_response_times(_frame(_opened("sdk", "alice", 1, at=10), _merged("sdk", "bob", "alice", 1, at=2)))

    assert prs.empty


def test_first_prs_follow_each_authors_earliest_prs_merged_or_not():
    """Cohort is by the author's own order, counting PRs that never merged."""
    records = [
        # alice opens #1 (never merged), #2, then #3: only #1 and #2 are her first two.
        _opened("sdk", "alice", 1, at=0),
        _opened("sdk", "alice", 2, at=24),
        _merged("sdk", "bob", "alice", 2, at=30),
        _opened("sdk", "alice", 3, at=48),
        _merged("sdk", "bob", "alice", 3, at=50),
        # bob's single PR is a first PR.
        _opened("sdk", "bob", 4, at=60),
        _merged("sdk", "alice", "bob", 4, at=61),
    ]
    prs = pr_response_times(_frame(*records), newcomer_max_prs=2)

    assert _one(prs, 2)["cohort"] == "first_prs"
    assert _one(prs, 3)["cohort"] == "later_prs"
    assert _one(prs, 4)["cohort"] == "first_prs"


@pytest.mark.parametrize("records", [[], [_opened("sdk", "alice", 1)], [_merged("sdk", "bob", "alice", 1, at=1)]])
def test_no_merged_pr_gives_an_empty_frame_with_the_schema(records):
    """With nothing to measure, callers still get the stable column schema."""
    prs = pr_response_times(_frame(*records))

    assert prs.empty
    assert list(prs.columns) == PR_RESPONSE_COLUMNS


def _prs_for_summary() -> pd.DataFrame:
    """Five sdk PRs (reviews after 1..4h; one unreviewed) plus one docs PR."""
    records = []
    for number, (review, merge) in enumerate([(1, 10), (2, 20), (3, 30), (4, 40), (None, 50)], start=1):
        records.append(_opened("sdk", f"dev{number}", number))
        if review is not None:
            records.append(_reviewed("sdk", "bob", f"dev{number}", number, at=review))
        records.append(_merged("sdk", "bob", f"dev{number}", number, at=merge))
    records += [
        _opened("docs", "eve", 1),
        _reviewed("docs", "bob", "eve", 1, at=100),
        _merged("docs", "bob", "eve", 1, at=200),
    ]
    return pr_response_times(_frame(*records), newcomer_max_prs=1)


def _cell(summary: pd.DataFrame, **match) -> pd.Series:
    selected = summary
    for column, value in match.items():
        selected = selected[selected[column] == value]
    assert len(selected) == 1, match
    return selected.iloc[0]


def test_summary_reports_medians_and_how_many_prs_were_reviewed():
    """The summary gives the median waits and how many merged PRs were reviewed at all."""
    summary = responsiveness_summary(_prs_for_summary(), [("all", None)])

    row = _cell(summary, period="all", cohort="all")
    assert list(summary.columns) == SUMMARY_COLUMNS
    assert row["merged_prs"] == 6
    assert row["reviewed_prs"] == 5
    assert row["reviewed_share"] == 83
    # Reviews at 1, 2, 3, 4 and 100 hours -> median 3; merges at 10, 20, 30, 40, 50, 200 -> 35.
    assert row["median_hours_to_first_review"] == pytest.approx(3)
    assert row["median_hours_to_merge"] == pytest.approx(35)


def test_p90_is_withheld_below_the_minimum_sample_and_reported_above_it():
    """A 90th percentile of a handful of PRs is just the maximum, so it is left empty."""
    few = _cell(responsiveness_summary(_prs_for_summary(), [("all", None)]), period="all", cohort="all")
    assert pd.isna(few["p90_hours_to_first_review"])
    assert pd.isna(few["p90_hours_to_merge"])

    records = []
    for number in range(1, 11):
        records += [
            _opened("sdk", f"dev{number}", number),
            _reviewed("sdk", "bob", f"dev{number}", number, at=number),
            _merged("sdk", "bob", f"dev{number}", number, at=number * 10),
        ]
    many = _cell(
        responsiveness_summary(pr_response_times(_frame(*records)), [("all", None)]),
        period="all",
        cohort="all",
    )
    assert many["p90_hours_to_first_review"] == pytest.approx(9.1)
    assert many["p90_hours_to_merge"] == pytest.approx(91)


def test_windows_select_prs_by_merge_time():
    """A window includes the PRs merged inside it, however long ago they were opened."""
    prs = pr_response_times(
        _frame(
            _opened("sdk", "alice", 1, at=0),
            _merged("sdk", "bob", "alice", 1, at=24),
            _opened("sdk", "carol", 2, at=24 * 20),
            _merged("sdk", "bob", "carol", 2, at=24 * 20 + 6),
        )
    )
    windows = [("all", None), ("7d", T0 + timedelta(days=20))]

    summary = responsiveness_summary(prs, windows)

    assert _cell(summary, period="all", cohort="all")["merged_prs"] == 2
    recent = _cell(summary, period="7d", cohort="all")
    assert recent["merged_prs"] == 1
    assert recent["median_hours_to_merge"] == pytest.approx(6)


def test_every_window_and_cohort_has_a_row_even_when_empty():
    """An empty cell is a row with zero PRs, so zero and missing are never confused."""
    prs = pr_response_times(_frame(_opened("sdk", "alice", 1), _merged("sdk", "bob", "alice", 1, at=3)))

    summary = responsiveness_summary(prs, [("all", None), ("7d", T0 + timedelta(days=400))])

    assert len(summary) == 6
    empty = _cell(summary, period="7d", cohort="first_prs")
    assert empty["merged_prs"] == 0
    assert empty["reviewed_share"] == 0
    assert pd.isna(empty["median_hours_to_merge"])


def test_cohorts_are_reported_separately():
    """First PRs and later PRs get their own rows alongside the overall one."""
    summary = responsiveness_summary(_prs_for_summary(), [("all", None)])

    first = _cell(summary, period="all", cohort="first_prs")
    assert first["merged_prs"] == 6  # every author here has exactly one PR
    assert _cell(summary, period="all", cohort="later_prs")["merged_prs"] == 0


def test_per_repo_summary_carries_the_repo_and_the_same_statistics():
    """The per-repo table is the same statistics keyed by repository."""
    summary = responsiveness_summary(_prs_for_summary(), [("all", None)], by_repo=True)

    assert list(summary.columns) == REPO_SUMMARY_COLUMNS
    assert sorted(summary["repo"].unique()) == ["org/docs", "org/sdk"]
    docs = _cell(summary, repo="org/docs", period="all", cohort="all")
    assert docs["merged_prs"] == 1
    assert docs["median_hours_to_first_review"] == pytest.approx(100)
    sdk = _cell(summary, repo="org/sdk", period="all", cohort="all")
    assert sdk["merged_prs"] == 5
    assert sdk["reviewed_share"] == 80


def test_summaries_of_nothing_keep_their_schema():
    """Empty input yields empty or zero-count tables with the documented columns."""
    empty = pr_response_times(_frame())

    assert list(responsiveness_summary(empty, [("all", None)], by_repo=True).columns) == REPO_SUMMARY_COLUMNS
    assert responsiveness_summary(empty, [("all", None)], by_repo=True).empty
    org_wide = responsiveness_summary(empty, [("all", None)])
    assert list(org_wide.columns) == SUMMARY_COLUMNS
    assert (org_wide["merged_prs"] == 0).all()
    assert list(monthly_responsiveness(empty).columns) == MONTHLY_COLUMNS
    assert monthly_responsiveness(empty).empty


def test_monthly_trend_groups_by_merge_month_and_omits_empty_months():
    """The trend is by merge month; a month with no merged PRs has no row."""
    prs = pr_response_times(
        _frame(
            _opened("sdk", "alice", 1, at=0),
            _reviewed("sdk", "bob", "alice", 1, at=4),
            _merged("sdk", "bob", "alice", 1, at=8),
            # 61 days after 1 June is 1 August: nothing is merged in July.
            _opened("sdk", "alice", 2, at=24 * 61),
            _reviewed("sdk", "bob", "alice", 2, at=24 * 61 + 2),
            _merged("sdk", "bob", "alice", 2, at=24 * 61 + 5),
        ),
    )

    monthly = monthly_responsiveness(prs)

    assert list(monthly.columns) == MONTHLY_COLUMNS
    assert monthly.loc[monthly["cohort"] == "all", "month"].tolist() == ["2026-06", "2026-08"]
    june = _cell(monthly, month="2026-06", cohort="all")
    assert june["merged_prs"] == 1
    assert june["median_hours_to_first_review"] == pytest.approx(4)
    assert june["median_hours_to_merge"] == pytest.approx(8)
    august = _cell(monthly, month="2026-08", cohort="all")
    assert august["median_hours_to_first_review"] == pytest.approx(2)
    assert august["median_hours_to_merge"] == pytest.approx(5)
