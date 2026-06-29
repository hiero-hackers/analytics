"""Tests for the contributor-activity heatmap build."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from hiero_analytics.data_sources.models import ContributorActivityRecord
from hiero_analytics.run_contributor_heatmap_org import (
    ACTIVITY_WEIGHTS,
    _build_activity_heatmap_dataframe,
    _save_activity_heatmap_chart,
)


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

    df = _build_activity_heatmap_dataframe(records, role_lookup)

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
    """Automation accounts (named bots and any [bot]-suffixed login) are dropped."""
    records = [
        _ev("alice", "authored_pull_request", 1),
        _ev("dependabot", "authored_pull_request", 2),
        _ev("coderabbitai", "reviewed_pull_request", 3),
        _ev("github-actions", "authored_pull_request", 4),
        _ev("renovate[bot]", "authored_pull_request", 5),
        _ev("CodeRabbit", "reviewed_pull_request", 6),  # case-insensitive
    ]
    df = _build_activity_heatmap_dataframe(records, {})
    assert list(df["contributor name"]) == ["alice"]  # only the human remains


def test_heatmap_dataframe_empty_records():
    """No records yields an empty frame that still carries the expected columns."""
    df = _build_activity_heatmap_dataframe([], {})
    assert df.empty
    assert "activity score" in df.columns


def test_save_heatmap_chart_writes_png(tmp_path):
    """A non-empty frame renders a PNG file on disk."""
    records = [_ev("alice", "authored_pull_request", 1), _ev("bob", "authored_issue", 2)]
    df = _build_activity_heatmap_dataframe(records, {})
    out = tmp_path / "heatmap.png"
    _save_activity_heatmap_chart(df, out)
    assert out.exists() and out.stat().st_size > 0


def test_save_heatmap_chart_skips_empty(tmp_path):
    """An empty frame writes nothing (no chart for no data)."""
    out = tmp_path / "none.png"
    _save_activity_heatmap_chart(pd.DataFrame(), out)
    assert not out.exists()
