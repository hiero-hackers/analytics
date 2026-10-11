"""Integration tests for the role-coverage pipeline orchestration (``main``)."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

import hiero_analytics.pipelines.role_coverage as runner
from hiero_analytics.dashboard_spec.governance import SECTION_SPECS
from hiero_analytics.data_sources.models import (
    ContributorActivityRecord,
    IssueTimelineEventRecord,
)
from hiero_analytics.export.data_api import _section_document

TEST_ORG = "test-org"

# Test data factories


def _test_activity(
    repo: str,
    actor: str,
    activity_type: str = "authored_pull_request",
    days_ago: int = 5,
    number: int = 1,
) -> ContributorActivityRecord:
    """Create a synthetic contributor activity record ``days_ago`` days in the past."""
    return ContributorActivityRecord(
        repo=repo,
        activity_type=activity_type,
        actor=actor,
        occurred_at=datetime.now(UTC) - timedelta(days=days_ago),
        target_type="pull_request",
        target_number=number,
    )


def _test_label_event(repo: str, actor: str, days_ago: int = 5) -> IssueTimelineEventRecord:
    """Create a synthetic issue label event ``days_ago`` days in the past."""
    return IssueTimelineEventRecord(
        repo=repo,
        issue_number=1,
        event_type="labeled",
        occurred_at=datetime.now(UTC) - timedelta(days=days_ago),
        label="bug",
        actor=actor,
    )


# Fixtures


@pytest.fixture
def governance_config() -> dict:
    """Minimal governance config: two repos, a maintain team, a write team, and tsc."""
    return {
        "teams": [
            {"name": "sdk-python-maintainers", "maintainers": ["alice"], "members": ["bob"]},
            {"name": "sdk-python-committers", "maintainers": [], "members": ["carol"]},
            {"name": "tsc", "maintainers": ["alice"], "members": []},
        ],
        "repositories": [
            {
                "name": "sdk-python",
                "teams": {"sdk-python-maintainers": "maintain", "sdk-python-committers": "write"},
            },
            {"name": "sdk-java", "teams": {"sdk-python-maintainers": "maintain"}},
        ],
    }


@pytest.fixture
def synthetic_activity() -> list[ContributorActivityRecord]:
    """Recent and older activity for the role-holders across both governed repos."""
    return [
        _test_activity(f"{TEST_ORG}/sdk-python", "alice", "authored_pull_request", days_ago=3, number=1),
        _test_activity(f"{TEST_ORG}/sdk-python", "alice", "merged_pull_request", days_ago=2, number=2),
        _test_activity(f"{TEST_ORG}/sdk-python", "bob", "reviewed_pull_request", days_ago=10, number=1),
        _test_activity(f"{TEST_ORG}/sdk-python", "carol", "authored_issue", days_ago=200, number=3),
        _test_activity(f"{TEST_ORG}/sdk-java", "alice", "authored_pull_request", days_ago=7, number=4),
        _test_activity(f"{TEST_ORG}/sdk-java", "bob", "reviewed_pull_request", days_ago=8, number=4),
    ]


@pytest.fixture
def synthetic_label_events() -> list[IssueTimelineEventRecord]:
    """A single label event so the label-derived profile columns are exercised."""
    return [_test_label_event(f"{TEST_ORG}/sdk-python", "alice", days_ago=4)]


def _patch_pipeline(monkeypatch, tmp_path, config, activity, label_events):
    """Redirect every external call ``main()`` makes to synthetic in-memory data."""
    mock_client = MagicMock()
    monkeypatch.setattr(
        "hiero_analytics.pipelines.role_coverage.org_context",
        lambda _org: (mock_client, tmp_path / "data"),
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.role_coverage.fetch_governance_config",
        lambda *_a, **_k: config,
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.role_coverage.load_contributor_activity",
        lambda _client, _org: activity,
    )
    monkeypatch.setattr(
        "hiero_analytics.pipelines.role_coverage.load_issue_label_events",
        lambda _client, _org: label_events,
    )

    def _fake_repo_dirs(repo_full: str) -> Path:
        slug = repo_full.replace("/", "_")
        repo_data_dir = tmp_path / "repo_data" / slug
        repo_data_dir.mkdir(parents=True, exist_ok=True)
        return repo_data_dir

    monkeypatch.setattr("hiero_analytics.pipelines.role_coverage.ensure_repo_dirs", _fake_repo_dirs)


# Tests


def test_main_creates_output_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    governance_config,
    synthetic_activity,
    synthetic_label_events,
):
    """Running main() should create the key org-level and per-repo coverage tables."""
    _patch_pipeline(monkeypatch, tmp_path, governance_config, synthetic_activity, synthetic_label_events)

    runner.main(TEST_ORG)

    data_dir = tmp_path / "data"
    expected_csvs = [
        "role_coverage_all.csv",
        "role_coverage_all_30d.csv",
        "team_activity_summary.csv",
        "team_activity_by_repo.csv",
        "role_coverage_globally_quiet.csv",
        "role_coverage_globally_quiet_30d.csv",
        "role_coverage_globally_quiet_7d.csv",
        "repo_activity_overview.csv",
        "tsc_activity_by_repo.csv",
        "maintainer_network_nodes.csv",
        "maintainer_network_edges.csv",
    ]
    for csv_file in expected_csvs:
        csv_path = data_dir / csv_file
        assert csv_path.exists(), f"CSV {csv_file} not created"
        assert os.path.getsize(csv_path) > 0, f"CSV {csv_file} is empty"

    # The combined coverage table has one row per (repo, holder) pair.
    coverage = (data_dir / "role_coverage_all.csv").read_text(encoding="utf-8")
    assert "alice" in coverage
    assert f"{TEST_ORG}/sdk-python" in coverage

    # The maintainer network links the two repos alice and bob both maintain, with laid-out positions.
    nodes = pd.read_csv(data_dir / "maintainer_network_nodes.csv")
    assert {"repo", "x", "y"} <= set(nodes.columns)
    assert len(nodes) == 2

    # Legacy per-repo files are written through the patched ensure_repo_dirs.
    repo_data_dir = tmp_path / "repo_data" / f"{TEST_ORG}_sdk-python"
    assert (repo_data_dir / "role_coverage.csv").exists()
    assert (repo_data_dir / "role_promotion_candidates.csv").exists()


def test_main_handles_empty_activity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    governance_config,
):
    """Running main() with no recorded activity should not crash.

    Role-holders exist in governance but have no activity anywhere, so every
    holder is quiet and the globally-quiet table still lists them.
    """
    _patch_pipeline(monkeypatch, tmp_path, governance_config, [], [])

    runner.main(TEST_ORG)

    data_dir = tmp_path / "data"
    assert (data_dir / "role_coverage_all.csv").exists()
    assert (data_dir / "team_activity_summary.csv").exists()
    quiet = (data_dir / "role_coverage_globally_quiet.csv").read_text(encoding="utf-8")
    assert "alice" in quiet

    coverage = pd.read_csv(data_dir / "role_coverage_all.csv")
    assert set(coverage["status"]) == {"quiet"}
    assert (coverage.filter(regex="_recent$") == 0).all().all()


@pytest.fixture
def historical_outputs(tmp_path, monkeypatch, governance_config):
    """A fixed history spanning every window, including never-active role holders."""
    now = datetime(2026, 10, 11, 12, tzinfo=UTC)

    class FixedClock:
        @staticmethod
        def now(_tz):
            return now

    monkeypatch.setattr(runner, "datetime", FixedClock)
    repo = f"{TEST_ORG}/sdk-python"
    records, labels = [], []
    for days in (5, 20, 150, 500):
        when = now - timedelta(days=days)
        for activity_type in (
            "authored_pull_request",
            "reviewed_pull_request",
            "merged_pull_request",
            "authored_issue",
        ):
            records.append(
                ContributorActivityRecord(
                    repo=repo,
                    actor="alice",
                    activity_type=activity_type,
                    occurred_at=when,
                    target_type="pull_request",
                    target_number=len(records) + 1,
                )
            )
        labels.append(
            IssueTimelineEventRecord(
                repo=repo,
                actor="alice",
                issue_number=len(labels) + 1,
                event_type="labeled",
                label="bug",
                occurred_at=when,
            )
        )
    # Enough reviews to exercise the load-share table's 20-action minimum.
    for actor, days in [("alice", 5)] * 25 + [("bob", 150), ("carol", 500)]:
        records.append(
            ContributorActivityRecord(
                repo=repo,
                actor=actor,
                activity_type="reviewed_pull_request",
                occurred_at=now - timedelta(days=days),
                target_type="pull_request",
                target_number=len(records) + 1,
            )
        )
    governance_config["teams"][0]["members"].append("never-active")
    _patch_pipeline(monkeypatch, tmp_path, governance_config, records, labels)
    runner.main(TEST_ORG)
    return tmp_path


def test_all_time_counts_include_history_beyond_a_year(historical_outputs):
    """All five counts use the full history; bounded windows remain independently counted."""
    data = historical_outputs / "data"
    count_columns = ["prs_recent", "reviews_recent", "merges_recent", "issues_recent", "labels_recent"]
    expected = {"": [4, 29, 4, 4, 4], "_7d": [1, 26, 1, 1, 1], "_30d": [2, 27, 2, 2, 2], "_365d": [3, 28, 3, 3, 3]}
    base = pd.read_csv(data / "role_coverage_all.csv").set_index(["repo", "user"])
    for suffix, counts in expected.items():
        frame = pd.read_csv(data / f"role_coverage_all{suffix}.csv").set_index(["repo", "user"])
        assert frame.loc[(f"{TEST_ORG}/sdk-python", "alice"), count_columns].tolist() == counts
        assert (base[count_columns].sort_index() >= frame[count_columns].sort_index()).all().all()
    for user in ("bob", "carol"):
        assert base.loc[(f"{TEST_ORG}/sdk-python", user), "status"] == "active"
    assert base.loc[(f"{TEST_ORG}/sdk-python", "never-active"), "status"] == "quiet"
    # Activity in one repo must not make its holder active in another.
    assert (base.loc[f"{TEST_ORG}/sdk-java", count_columns] == 0).all().all()
    assert set(base.loc[f"{TEST_ORG}/sdk-java", "status"]) == {"quiet"}
    assert base.loc[(f"{TEST_ORG}/sdk-python", "carol"), "days_since_active"] == 500


def test_all_time_repo_summaries_use_full_history(historical_outputs):
    """Activity, staffing and review-load summaries inherit the all-time counts and status."""
    data = historical_outputs / "data"
    overview = pd.read_csv(data / "repo_activity_overview.csv").set_index("repo")
    assert overview.loc["sdk-python", "actions_recent"] == 47
    assert overview.loc["sdk-python", "actions_all_time"] == 47
    assert overview.loc["sdk-python", "active_recent"] == 3
    assert overview.loc["sdk-python", "maintainer_actions_recent"] == 46
    assert overview.loc["sdk-python", "committer_actions_recent"] == 1
    risk = pd.read_csv(data / "maintainer_coverage_risk.csv").set_index("repo")
    assert "sdk-python" not in risk.index  # Both maintainers have recorded activity.
    assert risk.loc["sdk-java", "active_maintainers"] == 0
    load = pd.read_csv(data / "review_load_share.csv").set_index("repo")
    assert load.loc["sdk-python", "load_recent"] == 35
    assert load.loc["sdk-python", "mergers"] == 3
    assert load.loc["sdk-python", "top_carrier"] == "alice"
    assert load.loc["sdk-python", "top_pct"] == 94  # 33 of 35 reviews + merges.


def test_networks_and_legacy_coverage_keep_their_recent_window(historical_outputs):
    """The dashboard's all-time fix must not redefine the existing 90-day outputs."""
    data = historical_outputs / "data"
    legacy = pd.read_csv(historical_outputs / "repo_data" / f"{TEST_ORG}_sdk-python" / "role_coverage.csv").set_index(
        "user"
    )
    assert legacy.loc["alice", "prs_recent"] == 2
    assert legacy.loc["alice", "reviews_recent"] == 27
    assert legacy.loc["alice", "reviews_given"] == 29
    assert legacy.loc["bob", "status"] == legacy.loc["carol", "status"] == "quiet"
    for role, active in [("maintainer", 1), ("committer", 0)]:
        nodes = pd.read_csv(data / f"{role}_network_nodes.csv").set_index("repo")
        assert nodes.loc["sdk-python", "active_members"] == active


def test_api_publishes_corrected_base_and_bounded_periods(historical_outputs):
    """The same public columns carry all-time values and the independent period variants."""
    data = historical_outputs / "data"
    documents = {
        spec["id"]: _section_document(spec, {}, TEST_ORG, data)
        for spec in SECTION_SPECS
        if spec["id"] in {"repo", "repoactivity", "understaffed", "loadshare"}
    }
    repo = documents["repo"]
    alice = next(row for row in repo["rows"] if row["user"] == "alice" and row["repo"].endswith("/sdk-python"))
    assert alice["reviews_recent"] == 29
    year = next(
        row for row in repo["periods"]["365d"] if row["user"] == "alice" and row["repo"].endswith("/sdk-python")
    )
    assert year["reviews_recent"] == 28
    for document in documents.values():
        assert set(document["periods"]) == {"7d", "30d", "365d"}
        columns = {column["key"] for column in document["columns"]}
        for rows in [document["rows"], *document["periods"].values()]:
            assert all(set(row) == columns for row in rows)


@pytest.mark.parametrize("days", [7, 30, 365])
def test_period_count_boundary_is_inclusive(tmp_path, monkeypatch, governance_config, days):
    """An event at the cutoff counts; one just before it belongs only to wider windows."""
    now = datetime(2026, 10, 11, 12, tzinfo=UTC)

    class FixedClock:
        @staticmethod
        def now(_tz):
            return now

    monkeypatch.setattr(runner, "datetime", FixedClock)
    records = [
        ContributorActivityRecord(
            repo=f"{TEST_ORG}/sdk-python",
            actor="alice",
            activity_type="reviewed_pull_request",
            occurred_at=now - timedelta(days=days, seconds=offset),
            target_type="pull_request",
            target_number=offset + 1,
        )
        for offset in (0, 1)
    ]
    _patch_pipeline(monkeypatch, tmp_path, governance_config, records, [])
    runner.main(TEST_ORG)
    for suffix, expected in [("", 2), (f"_{days}d", 1)]:
        frame = pd.read_csv(tmp_path / "data" / f"role_coverage_all{suffix}.csv")
        alice = frame[(frame["user"] == "alice") & frame["repo"].str.endswith("/sdk-python")]
        assert alice["reviews_recent"].item() == expected
