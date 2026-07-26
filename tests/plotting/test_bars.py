"""Tests for the bar-chart helpers: rounded patches, annotation padding, file export."""

from __future__ import annotations

import matplotlib
import pandas as pd
import pytest
from matplotlib.patches import FancyBboxPatch

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from hiero_analytics.plotting.bars import (
    _compute_annotation_padding,
    _round_bar_patches,
    plot_bar,
)
from hiero_analytics.plotting.base import create_figure


def test_round_bar_patches_replaces_default_rectangles():
    """Rounded bars should be rendered with rounded box patches."""
    fig, ax = create_figure()
    bars = ax.bar(["A", "B"], [4, 6])

    _round_bar_patches(ax, list(bars.patches))

    rounded_patches = [patch for patch in ax.patches if isinstance(patch, FancyBboxPatch)]
    assert len(rounded_patches) == 2
    assert not any(bar.get_visible() for bar in bars.patches)

    plt.close(fig)


def test_compute_annotation_padding_uses_ratio_with_floor():
    """Bar annotations should keep a minimum offset on small charts."""
    assert _compute_annotation_padding(10) == pytest.approx(0.75)
    assert _compute_annotation_padding(100) == pytest.approx(1.5)


def test_plot_bar_writes_chart_file(tmp_path):
    """``plot_bar`` should export a non-empty chart asset."""
    bar_df = pd.DataFrame({"repo": ["mirror-node", "sdk-python", "solo"], "count": [24, 18, 12]})
    output = tmp_path / "difficulty_by_repo.png"

    plot_bar(bar_df, x_col="repo", y_col="count", title="Issues by Repository", output_path=output, rotate_x=30)

    assert output.exists() and output.stat().st_size > 0
