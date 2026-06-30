"""Tests for the contributor-activity heatmap matrix build."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from hiero_analytics.analysis.contributor_heatmap import (
    build_activity_heatmap_dataframe,
    build_repo_activity_heatmap,
    build_team_activity_heatmap,
    grouped_heatmap_chart_data,
    heatmap_chart_data,
)
from hiero_analytics.config.analysis import ACTIVITY_WEIGHTS
from hiero_analytics.data_sources.models import ContributorActivityRecord


def _ev(actor: str, activity_type: str, n: int, *, repo: str = "o/x") -> ContributorActivityRecord:
    """Build a contributor-activity record dated to now (inside the heatmap window)."""
    target_type = "issue" if activity_type == "authored_issue" else "pull_request"
    return ContributorActivityRecord(
        repo=repo,
        activity_type=activity_type,
        actor=actor,
        occurred_at=datetime.now(UTC),
        target_type=target_type,
        target_number=n,
    )


def test_heatmap_dataframe_scores_roles_and_sorts():
    """Scores are weighted sums, the governance role is labelled, rows sort by score."""
    records = [
        _ev("alice", "authored_pull_request", 1),  # prs created -> weight 3
        _ev("alice", "reviewed_pull_request", 2),  # reviews -> weight 3
        _ev("bob", "authored_issue", 3),  # issues -> weight 2
    ]
    role_lookup = {"x": {"alice": "maintainer"}}

    df = build_activity_heatmap_dataframe(records, role_lookup)

    month_cols = [c for c in df.columns if c not in {"contributor name", "role", "activity score"}]
    assert len(month_cols) == 6  # six-month window
    assert list(df["contributor name"]) == ["alice", "bob"]  # higher score first
    assert df.loc[0, "role"] == "Maintainer"  # from the governance lookup
    assert df.loc[1, "role"] == "General User"  # default when not in the lookup
    assert int(df.loc[0, "activity score"]) == ACTIVITY_WEIGHTS["prs created"] + ACTIVITY_WEIGHTS["reviews"]
    assert int(df.loc[1, "activity score"]) == ACTIVITY_WEIGHTS["issues"]
    # All activity is dated "now", so the month columns sum back to the score.
    assert df.loc[0, month_cols].sum() == df.loc[0, "activity score"]


def test_heatmap_excludes_bots():
    """Automation accounts (named bots and any [bot]/-bot login) are dropped."""
    records = [
        _ev("alice", "authored_pull_request", 1),
        _ev("dependabot", "authored_pull_request", 2),
        _ev("coderabbitai", "reviewed_pull_request", 3),
        _ev("github-actions", "authored_pull_request", 4),
        _ev("renovate[bot]", "authored_pull_request", 5),
        _ev("some-bot", "authored_pull_request", 6),  # -bot suffix
        _ev("CodeRabbit", "reviewed_pull_request", 7),  # case-insensitive
    ]
    df = build_activity_heatmap_dataframe(records, {})
    assert list(df["contributor name"]) == ["alice"]  # only the human remains


def test_heatmap_dataframe_empty_records():
    """No records yields an empty frame that still carries the expected columns."""
    df = build_activity_heatmap_dataframe([], {})
    assert df.empty
    assert "activity score" in df.columns


def test_heatmap_chart_data_extracts_matrix():
    """Chart data is the top rows as (values, row_labels, col_labels)."""
    records = [_ev("alice", "authored_pull_request", 1), _ev("bob", "authored_issue", 2)]
    df = build_activity_heatmap_dataframe(records, {})
    values, row_labels, col_labels = heatmap_chart_data(df)
    assert row_labels == ["alice", "bob"]
    assert len(col_labels) == 6
    assert values.shape == (2, 6)


def test_heatmap_chart_data_none_when_empty():
    """An empty frame produces no chart data."""
    assert heatmap_chart_data(pd.DataFrame()) is None


def test_repo_activity_heatmap_aggregates_and_excludes_bots():
    """Per-repo weighted scores sum the events; bots are excluded; busiest repo first."""
    records = [
        _ev("alice", "authored_pull_request", 1, repo="o/a"),  # prs created -> 3
        _ev("bob", "merged_pull_request", 2, repo="o/a"),       # prs merged -> 2
        _ev("carol", "authored_issue", 3, repo="o/b"),          # issues -> 2
        _ev("dependabot[bot]", "authored_pull_request", 4, repo="o/a"),  # bot -> excluded
    ]
    df = build_repo_activity_heatmap(records)

    by_repo = df.set_index("repo")
    assert by_repo.loc["a", "activity score"] == ACTIVITY_WEIGHTS["prs created"] + ACTIVITY_WEIGHTS["prs merged"]
    assert by_repo.loc["b", "activity score"] == ACTIVITY_WEIGHTS["issues"]
    assert df.iloc[0]["repo"] == "a"  # busiest first


def test_team_activity_heatmap_sums_members_with_overlap():
    """Team scores sum member activity; a shared member counts toward each team."""
    contrib = build_activity_heatmap_dataframe(
        [_ev("alice", "authored_pull_request", 1), _ev("bob", "authored_issue", 2)], {}
    )
    df = build_team_activity_heatmap(contrib, {"t1": {"alice", "bob"}, "t2": {"alice"}})

    by_team = df.set_index("team")
    assert by_team.loc["t1", "activity score"] == ACTIVITY_WEIGHTS["prs created"] + ACTIVITY_WEIGHTS["issues"]
    assert by_team.loc["t2", "activity score"] == ACTIVITY_WEIGHTS["prs created"]  # alice counted in both
    assert df.iloc[0]["team"] == "t1"  # busiest first


def test_team_activity_heatmap_drops_inactive_teams():
    """A team whose members have no recorded activity is omitted."""
    contrib = build_activity_heatmap_dataframe([_ev("alice", "authored_issue", 1)], {})
    assert build_team_activity_heatmap(contrib, {"empty": {"zoe"}}).empty


def test_grouped_heatmap_chart_data_shape_and_empty():
    """Chart data returns aligned values/labels keyed on the given column, None when empty."""
    df = build_repo_activity_heatmap(
        [_ev("alice", "authored_pull_request", 1, repo="o/a"), _ev("bob", "authored_issue", 2, repo="o/b")]
    )
    values, rows, cols = grouped_heatmap_chart_data(df, "repo", top_rows=5)
    assert rows == ["a", "b"]  # a (3) busier than b (2)
    assert values.shape[0] == 2 and len(cols) >= 1
    assert grouped_heatmap_chart_data(pd.DataFrame(columns=["repo", "activity score"]), "repo") is None
