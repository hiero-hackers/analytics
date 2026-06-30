"""Tests for the heatmap chart renderer."""

from __future__ import annotations

import numpy as np

from hiero_analytics.plotting.heatmap import plot_heatmap


def test_plot_heatmap_writes_png(tmp_path):
    """A non-empty matrix renders a PNG file on disk."""
    out = tmp_path / "heatmap.png"
    plot_heatmap(
        np.array([[1.0, 2.0], [3.0, 0.0]]),
        row_labels=["alice", "bob"],
        col_labels=["2024-01", "2024-02"],
        output_path=out,
        title="Activity",
        xlabel="Month",
        ylabel="Contributor",
        value_label="score",
    )
    assert out.exists() and out.stat().st_size > 0


def test_plot_heatmap_skips_empty(tmp_path):
    """An empty matrix writes nothing (no chart for no data)."""
    out = tmp_path / "none.png"
    plot_heatmap(
        np.empty((0, 0)),
        row_labels=[],
        col_labels=[],
        output_path=out,
        title="Activity",
        xlabel="Month",
        ylabel="Contributor",
        value_label="score",
    )
    assert not out.exists()
