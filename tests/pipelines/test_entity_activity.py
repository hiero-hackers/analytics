"""The entity_activity pipeline writes the detail views' tables from persisted activity."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

import hiero_analytics.pipelines.entity_activity as runner
from hiero_analytics.dashboard_spec import entities as spec
from hiero_analytics.data_sources.models import ContributorActivityRecord, IssueTimelineEventRecord


def _act(repo: str, actor: str, activity_type: str, days_ago: int) -> ContributorActivityRecord:
    return ContributorActivityRecord(
        repo=f"test-org/{repo}",
        activity_type=activity_type,
        actor=actor,
        occurred_at=datetime.now(UTC) - timedelta(days=days_ago),
        target_type="pull_request",
        target_number=1,
        target_author=actor,
    )


def _patch(monkeypatch, stub_pipeline_context, records, labels):
    _, data_dir = stub_pipeline_context(runner)
    monkeypatch.setattr(runner, "load_contributor_activity", lambda _client, _org: records)
    monkeypatch.setattr(runner, "load_issue_label_events", lambda _client, _org: labels)
    return data_dir


def test_writes_every_table_with_windows_and_a_freshness_sidecar(monkeypatch, stub_pipeline_context):
    """Every table is written per window, with its sidecar and window stamps."""
    records = [
        _act("sdk", "alice", "authored_pull_request", 2),
        _act("sdk", "bob", "merged_pull_request", 40),
        _act("docs", "alice", "authored_issue", 400),
    ]
    labels = [
        IssueTimelineEventRecord(
            repo="test-org/sdk",
            issue_number=3,
            event_type="labeled",
            occurred_at=datetime.now(UTC) - timedelta(days=1),
            label="bug",
            actor="carol",
        )
    ]
    data_dir = _patch(monkeypatch, stub_pipeline_context, records, labels)

    runner.main("test-org")

    for name in spec.ENTITY_FILES:
        assert (data_dir / name).exists(), name
        assert (data_dir / f"{name}.meta.json").exists(), name
    repos = pd.read_csv(data_dir / spec.REPO_ACTIVITY_FILE)
    assert set(repos["period"]) == {"all", "7d", "30d", "365d"}
    sdk = repos[repos["repo"] == "test-org/sdk"].set_index("period")
    assert sdk.loc["all", "active_contributors"] == 3
    assert sdk.loc["7d", "active_contributors"] == 2  # alice's PR and carol's label; bob merged 40 days ago
    assert "30d" in sdk.index and "7d" in sdk.index
    # docs was last active 400 days ago: only its all-time row exists.
    assert repos[repos["repo"] == "test-org/docs"]["period"].tolist() == ["all"]
    # One window end for every row, and the org's latest tracked event beside it.
    assert repos["window_end"].nunique() == 1
    assert repos["data_through"].nunique() == 1


def test_an_org_with_no_activity_writes_empty_tables(monkeypatch, stub_pipeline_context):
    """An org with no tracked activity still gets its (empty) tables."""
    data_dir = _patch(monkeypatch, stub_pipeline_context, [], [])
    runner.main("test-org")
    assert pd.read_csv(data_dir / spec.REPO_ACTIVITY_FILE).empty
    assert pd.read_csv(data_dir / spec.CONTRIBUTOR_MONTHLY_FILE).empty
