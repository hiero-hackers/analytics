"""Tests for the bar-chart helpers: rounded patches, annotation padding, file export."""

from __future__ import annotations

import matplotlib
import pandas as pd
import pytest
from matplotlib.patches import FancyBboxPatch

matplotlib.use("Agg")

import matplotlib.pyplot as plt

import hiero_analytics.plotting.bars as bars
from hiero_analytics.plotting.bars import (
    _compute_annotation_padding,
    _round_bar_patches,
    plot_bar,
)
from hiero_analytics.plotting.base import create_figure


def _capture_plot_bar(monkeypatch, tmp_path, df, *, horizontal):
    captured = {}
    monkeypatch.setattr(bars, "finalize_chart", lambda **kwargs: captured.update(kwargs))
    plot_bar(
        df,
        x_col="organisation",
        y_col="repos",
        title="Single-employer repositories",
        output_path=tmp_path / "bar.png",
        horizontal=horizontal,
    )
    return captured


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
    assert _compute_annotation_padding(2) == pytest.approx(0.2)
    assert _compute_annotation_padding(10) == pytest.approx(0.75)
    assert _compute_annotation_padding(100) == pytest.approx(1.5)


def test_plot_bar_writes_chart_file(tmp_path):
    """``plot_bar`` should export a non-empty chart asset."""
    bar_df = pd.DataFrame({"repo": ["mirror-node", "sdk-python", "solo"], "count": [24, 18, 12]})
    output = tmp_path / "difficulty_by_repo.png"

    plot_bar(bar_df, x_col="repo", y_col="count", title="Issues by Repository", output_path=output, rotate_x=30)

    assert output.exists() and output.stat().st_size > 0


def test_plot_bar_orientation_override_and_heuristic_fallback(monkeypatch, tmp_path):
    """Explicit orientation wins, while None retains the long-label heuristic."""
    long_labels = pd.DataFrame({"organisation": ["DSR Corporation", "Hashgraph"], "repos": [2, 1]})
    short_labels = pd.DataFrame({"organisation": ["Hashgraph", "BlockyDevs"], "repos": [2, 1]})

    assert _capture_plot_bar(monkeypatch, tmp_path, long_labels, horizontal=False)["grid_axis"] == "y"
    assert _capture_plot_bar(monkeypatch, tmp_path, short_labels, horizontal=True)["grid_axis"] == "x"
    assert _capture_plot_bar(monkeypatch, tmp_path, long_labels, horizontal=None)["grid_axis"] == "x"
    assert _capture_plot_bar(monkeypatch, tmp_path, short_labels, horizontal=None)["grid_axis"] == "y"


def test_small_vertical_bar_keeps_annotations_inside_integer_value_axis(monkeypatch, tmp_path):
    """Low count labels need headroom and count ticks must not become fractional."""
    frame = pd.DataFrame({"organisation": ["Hashgraph", "BlockyDevs"], "repos": [2, 1]})

    captured = _capture_plot_bar(monkeypatch, tmp_path, frame, horizontal=False)
    ax = captured["ax"]
    lower, upper = ax.get_ylim()
    annotations = [text for text in ax.texts if text.get_text() in {"1", "2"}]

    assert len(annotations) == 2
    assert all(lower <= text.get_position()[1] <= upper for text in annotations)

    captured["fig"].canvas.draw()
    tick_labels = [label.get_text() for label in ax.get_yticklabels() if label.get_text()]
    assert tick_labels
    assert all("." not in label for label in tick_labels)
