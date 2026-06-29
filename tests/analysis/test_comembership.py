"""Tests for the repo co-membership network builder."""

from __future__ import annotations

import pandas as pd

from hiero_analytics.analysis.comembership import build_comembership_network, role_membership


def _row(repo, user, role="maintainer", status="active"):
    return {"repo": repo, "user": user, "granted_role": role, "status": status}


def test_role_membership_filters_role_and_marks_active():
    """role_membership keeps only the chosen role and flags active by status."""
    coverage = pd.DataFrame(
        [
            _row("o/a", "alice", "maintainer", "active"),
            _row("o/a", "bob", "maintainer", "quiet"),
            _row("o/a", "carol", "committer", "active"),
        ]
    )
    m = role_membership(coverage, "maintainer")
    assert set(m["user"]) == {"alice", "bob"}  # committer excluded
    assert m.set_index("user").loc["alice", "active"]
    assert not m.set_index("user").loc["bob", "active"]


def test_nodes_count_active_and_total_members():
    """Nodes carry active and total member counts per repo (bare repo name)."""
    membership = pd.DataFrame(
        [
            {"repo": "o/a", "user": "alice", "active": True},
            {"repo": "o/a", "user": "bob", "active": False},
            {"repo": "o/b", "user": "alice", "active": True},
        ]
    )
    nodes, _ = build_comembership_network(membership, min_shared=1)
    a = nodes[nodes["repo"] == "a"].iloc[0]
    assert a["total_members"] == 2
    assert a["active_members"] == 1  # only alice


def test_edges_are_shared_members_above_threshold():
    """Two repos link when they share members; weak links drop below min_shared."""
    membership = pd.DataFrame(
        [
            {"repo": "a", "user": "alice", "active": True}, {"repo": "a", "user": "bob", "active": True},
            {"repo": "b", "user": "alice", "active": True}, {"repo": "b", "user": "bob", "active": True},
            {"repo": "c", "user": "alice", "active": True},  # a–c share only alice (1)
        ]
    )
    _, edges = build_comembership_network(membership, min_shared=2)
    pairs = {tuple(sorted((r.repo_a, r.repo_b))): r.shared for r in edges.itertuples()}
    assert pairs == {("a", "b"): 2}


def test_empty_membership_returns_empty():
    """An empty membership yields empty nodes and edges with the right columns."""
    nodes, edges = build_comembership_network(pd.DataFrame())
    assert nodes.empty and "active_members" in nodes.columns
    assert edges.empty and "shared" in edges.columns
