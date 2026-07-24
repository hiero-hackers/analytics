"""Integration tests for the org difficulty analytics pipeline runner."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import matplotlib
import pytest

matplotlib.use("Agg")

import hiero_analytics.pipelines.difficulty as runner
from hiero_analytics.data_sources.models import IssueRecord, IssueTimelineEventRecord

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

    expected_csvs = [
        "difficulty_distribution_30_days.csv",
        "difficulty_by_repo_30_days.csv",
    ]
    for csv_file in expected_csvs:
        csv_path = data_dir / csv_file
        assert csv_path.exists(), f"CSV {csv_file} not created"
        assert os.path.getsize(csv_path) > 0, f"CSV {csv_file} is empty"

    chart_path = charts_dir / "difficulty_by_repo_30_days.png"
    assert chart_path.exists(), "Chart difficulty_by_repo_30_days.png not created"
    assert os.path.getsize(chart_path) > 0, "Chart difficulty_by_repo_30_days.png is empty"


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

    assert (data_dir / "difficulty_distribution_30_days.csv").exists()
    assert (charts_dir / "difficulty_by_repo_30_days.png").exists()
