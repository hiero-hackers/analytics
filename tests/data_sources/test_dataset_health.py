"""Tests for the dataset refresh record and health verdict (``dataset_health``)."""

from __future__ import annotations

from hiero_analytics.data_sources import dataset_health
from hiero_analytics.data_sources.dataset_health import (
    HOLD_FAIL_AFTER,
    MONOTONIC_WARN_AFTER,
    DatasetRefresh,
    problems,
    render_markdown,
    summary,
    warnings,
)


def _refresh(**changes) -> DatasetRefresh:
    return DatasetRefresh(**{"dataset": "issues_org_all", "rows_before": 10, "rows_after": 12, **changes})


def test_a_clean_refresh_is_healthy_with_nothing_to_say():
    """Rows went up, nothing held, lost, overdue or deferred."""
    block = summary([_refresh(full_refreshed=["org/a"])])

    assert block["healthy"] is True
    assert block["problems"] == [] and block["warnings"] == []
    assert block["datasets"]["issues_org_all"]["full_refreshed"] == ["org/a"]


def test_a_hold_warns_until_it_has_lasted_the_threshold_then_fails():
    """One or two held runs are a warning; the third in a row fails the check."""
    almost = [_refresh(held={"org/a": HOLD_FAIL_AFTER - 1})]
    reached = [_refresh(held={"org/a": HOLD_FAIL_AFTER})]

    assert problems(almost) == []
    assert warnings(almost) == [f"issues_org_all: org/a held this run ({HOLD_FAIL_AFTER - 1} in a row)"]
    assert problems(reached) == [f"issues_org_all: org/a has been held for {HOLD_FAIL_AFTER} runs in a row"]


def test_rows_lost_outside_a_full_refresh_fail():
    """A delta can only add or update rows, so a loss it cannot explain fails the check."""
    assert problems([_refresh(unexplained_loss={"org/a": 4})]) == [
        "issues_org_all: org/a lost 4 rows without a full refresh or retirement"
    ]


def test_an_overdue_full_refresh_fails():
    """A repo past its window plus the grace period means the self-heal is not keeping up."""
    assert problems([_refresh(overdue={"org/a": "2026-09-01T00:00:00+00:00"})]) == [
        "issues_org_all: org/a has not been fully refreshed since 2026-09-01T00:00:00+00:00"
    ]


def test_deferrals_and_a_long_growth_streak_only_warn():
    """Monotonic growth is the self-heal's symptom, but event datasets are append-only, so it warns."""
    refreshes = [_refresh(deferred=["org/a", "org/b"], runs_without_shrink=MONOTONIC_WARN_AFTER)]

    assert problems(refreshes) == []
    assert warnings(refreshes) == [
        "issues_org_all: 2 due full refreshes deferred by the nightly budget",
        f"issues_org_all: has not shrunk in {MONOTONIC_WARN_AFTER} runs",
    ]


def test_record_keeps_the_latest_refresh_per_dataset_and_forget_clears():
    """A dataset fetched twice in one run (two pipelines) reports its last refresh."""
    dataset_health.record(_refresh(rows_after=12))
    dataset_health.record(_refresh(rows_after=13))
    dataset_health.record(DatasetRefresh(dataset="events_org_all", rows_before=0, rows_after=5))

    assert [(r.dataset, r.rows_after) for r in dataset_health.recorded()] == [
        ("events_org_all", 5),
        ("issues_org_all", 13),
    ]
    dataset_health.forget()
    assert dataset_health.recorded() == []


def test_the_summary_section_names_the_verdict_and_tabulates_each_dataset():
    """The job summary says whether the check fails, lists why, and counts each dataset's changes."""
    block = summary([_refresh(full_refreshed=["org/a", "org/b"], backfilled=["org/b"], held={"org/c": 3})])

    markdown = render_markdown(block)

    assert markdown.startswith("## Dataset refresh")
    assert "unhealthy" in markdown
    assert "- issues_org_all: org/c has been held for 3 runs in a row" in markdown
    assert "| issues_org_all | 10 | 12 | 2 | 1 | 0 | 1 | 0 |" in markdown


def test_no_section_when_nothing_was_refreshed():
    """An offline run refreshes nothing, so the job summary gets no empty table."""
    assert render_markdown(summary([])) == ""
