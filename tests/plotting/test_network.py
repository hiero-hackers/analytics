"""Smoke test for the co-membership network chart renderer."""

from __future__ import annotations

import pandas as pd

from hiero_analytics.plotting.network import render_comembership_network


def test_renders_png(tmp_path):
    """A non-empty network writes a PNG file; an empty one writes nothing."""
    nodes = pd.DataFrame(
        [
            {"repo": "hiero-sdk-python", "active_members": 3, "total_members": 4},
            {"repo": "hiero-consensus-node", "active_members": 1, "total_members": 2},
            {"repo": "governance", "active_members": 2, "total_members": 2},
        ]
    )
    edges = pd.DataFrame([{"repo_a": "hiero-sdk-python", "repo_b": "governance", "shared": 2}])

    out = tmp_path / "net.png"
    assert render_comembership_network(nodes, edges, out, title="t", member_label="maintainers") is True
    assert out.exists() and out.stat().st_size > 0

    empty = tmp_path / "none.png"
    assert render_comembership_network(pd.DataFrame(), edges, empty, title="t", member_label="x") is False
    assert not empty.exists()


def test_does_not_call_tight_layout(monkeypatch, tmp_path):
    """Network renderer must not call tight_layout()."""
    nodes = pd.DataFrame(
        [
            {"repo": "hiero-sdk-python", "active_members": 3, "total_members": 4},
            {"repo": "hiero-consensus-node", "active_members": 1, "total_members": 2},
            {"repo": "governance", "active_members": 2, "total_members": 2},
        ]
    )
    edges = pd.DataFrame([{"repo_a": "hiero-sdk-python", "repo_b": "governance", "shared": 2}])

    def fail_tight_layout(*args, **kwargs):
        raise AssertionError("tight_layout() should not be called")

    monkeypatch.setattr(
        "matplotlib.figure.Figure.tight_layout",
        fail_tight_layout,
    )

    output = tmp_path / "network.png"

    assert (
        render_comembership_network(
            nodes,
            edges,
            output,
            title="t",
            member_label="x",
        )
        is True
    )
    assert output.exists()
