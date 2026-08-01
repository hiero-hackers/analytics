"""Integration tests for the event-based difficulty-over-time pipeline runner."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import matplotlib
import pytest

matplotlib.use("Agg")

import hiero_analytics.pipelines.difficulty_over_time as runner
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


@pytest.fixture
def mock_github_client():
    """Mock GitHubClient."""
    return MagicMock()


def _patch_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mock_client,
    issues: list[IssueRecord],
    events: list[IssueTimelineEventRecord],
) -> None:
    """Redirect the pipeline preamble to tmp_path and stub the GitHub fetches."""
    monkeypatch.setattr(
        "hiero_analytics.pipelines.difficulty_over_time.org_context",
        lambda _org: (mock_client, tmp_path / "data", tmp_path / "charts"),
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.difficulty_over_time.fetch_org_issues_graphql",
        lambda _client, **_kwargs: issues,
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.difficulty_over_time.fetch_org_issue_label_events_graphql",
        lambda _client, **_kwargs: events,
    )


# Tests


def test_main_creates_output_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_github_client,
):
    """Running main() should create the weekly difficulty-over-time CSV and chart."""
    issues = [
        # Open issues created within the 365-day window whose current difficulty
        # label has a matching recorded ``labeled`` event.
        _test_issue("hiero-ledger/repo-one", 1, ["beginner"], created_days_ago=100),
        _test_issue("hiero-ledger/repo-one", 2, ["advanced"], created_days_ago=200),
        # Untriaged issue: only the "all issues" outputs should count it.
        _test_issue("hiero-ledger/repo-one", 3, [], created_days_ago=50),
    ]
    events = [
        _test_label_event("hiero-ledger/repo-one", 1, "beginner", days_ago=90),
        _test_label_event("hiero-ledger/repo-one", 2, "advanced", days_ago=180),
    ]
    _patch_pipeline(monkeypatch, tmp_path, mock_github_client, issues, events)

    runner.main()

    for stem in (
        "difficulty_over_time_event_based_weekly",
        "difficulty_over_time_all_event_based_weekly",
    ):
        csv_path = tmp_path / "data" / f"{stem}.csv"
        chart_path = tmp_path / "charts" / f"{stem}.png"

        assert csv_path.exists(), f"CSV {stem}.csv not created"
        assert os.path.getsize(csv_path) > 0, f"CSV {stem}.csv is empty"
        assert chart_path.exists(), f"Chart {stem}.png not created"
        assert os.path.getsize(chart_path) > 0, f"Chart {stem}.png is empty"

    # Only the "all" variant carries the unknown bucket.
    labelled_header = (tmp_path / "data" / "difficulty_over_time_event_based_weekly.csv").read_text().splitlines()[0]
    all_header = (tmp_path / "data" / "difficulty_over_time_all_event_based_weekly.csv").read_text().splitlines()[0]
    assert labelled_header == "date,gfi,beginner,intermediate,advanced"
    assert all_header == "date,unknown,gfi,beginner,intermediate,advanced"


def test_main_handles_empty_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_github_client,
):
    """Running main() with no issues or events should return early without crashing."""
    _patch_pipeline(monkeypatch, tmp_path, mock_github_client, issues=[], events=[])

    # Should not raise an exception
    runner.main()

    # No series data -> the pipeline exits before writing any outputs.
    assert not (tmp_path / "data" / "difficulty_over_time_event_based_weekly.csv").exists()
    assert not (tmp_path / "charts" / "difficulty_over_time_event_based_weekly.png").exists()
    assert not (tmp_path / "data" / "difficulty_over_time_all_event_based_weekly.csv").exists()
    assert not (tmp_path / "charts" / "difficulty_over_time_all_event_based_weekly.png").exists()
