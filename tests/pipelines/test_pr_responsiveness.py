"""The pr_responsiveness pipeline writes the wait tables from persisted activity."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

import hiero_analytics.pipelines.pr_responsiveness as runner
from hiero_analytics.data_sources.models import ContributorActivityRecord

NOW = datetime.now(UTC)


def _act(repo: str, actor: str, activity_type: str, hours_ago: float, number: int, author: str):
    return ContributorActivityRecord(
        repo=f"test-org/{repo}",
        activity_type=activity_type,
        actor=actor,
        occurred_at=NOW - timedelta(hours=hours_ago),
        target_type="pull_request",
        target_number=number,
        target_author=author,
    )


def _patch(monkeypatch, stub_pipeline_context, records):
    _, data_dir = stub_pipeline_context(runner)
    monkeypatch.setattr(runner, "load_contributor_activity", lambda _client, _org: records)
    return data_dir


def test_writes_the_three_tables_with_sidecars_and_window_stamps(monkeypatch, stub_pipeline_context):
    """Org-wide, per-repo and monthly tables are written from the persisted events."""
    records = [
        # alice's PR opened 30h ago, reviewed 6h in, merged 24h in.
        _act("sdk", "alice", "authored_pull_request", 30, 1, "alice"),
        _act("sdk", "bob", "reviewed_pull_request", 24, 1, "alice"),
        _act("sdk", "bob", "merged_pull_request", 6, 1, "alice"),
        # A PR from 400 days ago: all-time only.
        _act("docs", "carol", "authored_pull_request", 400 * 24, 7, "carol"),
        _act("docs", "bob", "merged_pull_request", 400 * 24 - 10, 7, "carol"),
    ]
    data_dir = _patch(monkeypatch, stub_pipeline_context, records)

    runner.main("test-org")

    for name in (
        runner.PR_RESPONSIVENESS_FILE,
        runner.PR_RESPONSIVENESS_BY_REPO_FILE,
        runner.PR_RESPONSIVENESS_MONTHLY_FILE,
    ):
        assert (data_dir / name).exists(), name
        assert (data_dir / f"{name}.meta.json").exists(), name

    overall = pd.read_csv(data_dir / runner.PR_RESPONSIVENESS_FILE).set_index(["period", "cohort"])
    assert set(overall.index.get_level_values("period")) == {"all", "7d", "30d", "365d"}
    assert overall.loc[("all", "all"), "merged_prs"] == 2
    assert overall.loc[("7d", "all"), "merged_prs"] == 1
    assert overall.loc[("7d", "all"), "median_hours_to_first_review"] == 6
    assert overall.loc[("7d", "all"), "median_hours_to_merge"] == 24
    assert overall["window_end"].nunique() == 1

    by_repo = pd.read_csv(data_dir / runner.PR_RESPONSIVENESS_BY_REPO_FILE)
    assert set(by_repo["repo"]) == {"test-org/sdk", "test-org/docs"}


def test_an_org_with_no_activity_writes_empty_tables(monkeypatch, stub_pipeline_context):
    """No merged PRs still produces the tables, with zero counts and no statistics."""
    data_dir = _patch(monkeypatch, stub_pipeline_context, [])

    runner.main("test-org")

    overall = pd.read_csv(data_dir / runner.PR_RESPONSIVENESS_FILE)
    assert (overall["merged_prs"] == 0).all()
    assert pd.read_csv(data_dir / runner.PR_RESPONSIVENESS_BY_REPO_FILE).empty
    assert pd.read_csv(data_dir / runner.PR_RESPONSIVENESS_MONTHLY_FILE).empty
