"""Integration tests for the org difficulty analytics pipeline runner."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import matplotlib
import pytest

matplotlib.use("Agg")

import hiero_analytics.pipelines.difficulty as runner
from hiero_analytics.data_sources.models import IssueRecord, IssueTimelineEventRecord
from hiero_analytics.domain.periods import ACTIVITY_PERIODS

# The shared span vocabulary: the all-time base plus one suffix per period.
SPAN_SUFFIXES = [""] + [f"_{period.key}" for period in ACTIVITY_PERIODS]

# Test data factories


def _test_issue(
    repo: str,
    number: int,
    labels: list[str],
    created_days_ago: int,
) -> IssueRecord:
    """Create an open test issue record created ``created_days_ago`` days ago."""
    return IssueRecord(
        repo=repo,
        number=number,
        title=f"Issue {number}",
        state="OPEN",
        created_at=datetime.now(UTC) - timedelta(days=created_days_ago),
        closed_at=None,
        labels=labels,
    )


def _test_label_event(
    repo: str,
    number: int,
    label: str,
    days_ago: int,
) -> IssueTimelineEventRecord:
    """Create a ``labeled`` timeline event that occurred ``days_ago`` days ago."""
    return IssueTimelineEventRecord(
        repo=repo,
        issue_number=number,
        event_type="labeled",
        occurred_at=datetime.now(UTC) - timedelta(days=days_ago),
        label=label,
        actor="alice",
    )


# Fixtures


def _stub_fetches(
    monkeypatch: pytest.MonkeyPatch,
    issues: list[IssueRecord],
    events: list[IssueTimelineEventRecord],
) -> None:
    """Stub the pipeline's GitHub fetches (the preamble is stubbed via the fixture)."""
    monkeypatch.setattr(
        "hiero_analytics.pipelines.difficulty.fetch_org_issues_graphql",
        lambda _client, **_kwargs: issues,
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.difficulty.fetch_org_issue_label_events_graphql",
        lambda _client, **_kwargs: events,
    )


# Tests


def test_main_creates_output_files(monkeypatch: pytest.MonkeyPatch, stub_pipeline_context):
    """Running main() should create the difficulty CSVs and stacked-bar chart."""
    issues = [
        # Old issue whose difficulty label was applied within the 30-day window.
        _test_issue("hiero-ledger/repo-one", 1, ["good first issue"], created_days_ago=60),
        # Newly created, still-untriaged issue -> Unknown bucket.
        _test_issue("hiero-ledger/repo-two", 2, [], created_days_ago=5),
    ]
    events = [
        _test_label_event("hiero-ledger/repo-one", 1, "good first issue", days_ago=10),
    ]
    _, data_dir, charts_dir = stub_pipeline_context(runner)
    _stub_fetches(monkeypatch, issues, events)

    runner.main()

    for suffix in SPAN_SUFFIXES:
        expected_csvs = [
            f"difficulty_distribution{suffix}.csv",
            f"difficulty_by_repo{suffix}.csv",
        ]
        for csv_file in expected_csvs:
            csv_path = data_dir / csv_file
            assert csv_path.exists(), f"CSV {csv_file} not created"
            assert os.path.getsize(csv_path) > 0, f"CSV {csv_file} is empty"

        chart_path = charts_dir / f"difficulty_by_repo{suffix}.png"
        assert chart_path.exists(), f"Chart difficulty_by_repo{suffix}.png not created"
        assert os.path.getsize(chart_path) > 0, f"Chart difficulty_by_repo{suffix}.png is empty"


def test_windows_scope_their_own_labeling_activity(monkeypatch: pytest.MonkeyPatch, stub_pipeline_context):
    """An issue labelled outside a span is excluded from it but counted by wider ones."""
    issues = [
        # Labelled 60 days ago: outside the 1-month span, inside 1 year and all time.
        _test_issue("hiero-ledger/repo-one", 1, ["good first issue"], created_days_ago=120),
    ]
    events = [
        _test_label_event("hiero-ledger/repo-one", 1, "good first issue", days_ago=60),
    ]
    _, data_dir, _ = stub_pipeline_context(runner)
    _stub_fetches(monkeypatch, issues, events)

    runner.main()

    def _gfi_count(suffix: str) -> int:
        rows = (data_dir / f"difficulty_distribution{suffix}.csv").read_text().splitlines()[1:]
        return sum(int(row.split(",")[1]) for row in rows if row.startswith("Good First Issue,"))

    assert _gfi_count("_7d") == 0
    assert _gfi_count("_30d") == 0
    assert _gfi_count("_365d") == 1
    assert _gfi_count("") == 1


def test_main_handles_empty_timeline_events(monkeypatch: pytest.MonkeyPatch, stub_pipeline_context):
    """Running main() with no timeline events should not crash.

    Recently created issues still qualify via the creation-date fallbacks (a
    labeled issue created inside the window, plus the Unknown bucket), so the
    pipeline completes and writes its outputs.
    """
    issues = [
        # Created within the window and already labeled -> fallback inclusion.
        _test_issue("hiero-ledger/repo-one", 1, ["beginner"], created_days_ago=10),
        # Created within the window without a difficulty label -> Unknown bucket.
        _test_issue("hiero-ledger/repo-one", 2, [], created_days_ago=3),
    ]
    _, data_dir, charts_dir = stub_pipeline_context(runner)
    _stub_fetches(monkeypatch, issues, events=[])

    # Should not raise an exception
    runner.main()

    for suffix in SPAN_SUFFIXES:
        assert (data_dir / f"difficulty_distribution{suffix}.csv").exists()
        assert (charts_dir / f"difficulty_by_repo{suffix}.png").exists()
