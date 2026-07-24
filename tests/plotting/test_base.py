"""Tests for shared chart scaffolding: figure creation, axis styling, legend placement."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from hiero_analytics.plotting.base import (
    adaptive_legend_placement,
    create_figure,
    style_axes,
)


def test_adaptive_legend_placement_few_items_sits_below():
    """Six-or-fewer entries get a wide bottom legend, ncol capped at 4."""
    placement = adaptive_legend_placement(3)
    assert placement["legend_loc"] == "lower center"
    assert placement["legend_ncol"] == 3
    assert placement["legend_bbox_to_anchor"] == (0.5, -0.14)
    assert placement["layout_rect"] == (0.0, 0.14, 1.0, 1.0)
    assert adaptive_legend_placement(6)["legend_ncol"] == 4


def test_adaptive_legend_placement_many_items_move_right():
    """More than six entries switch to a single right-hand column."""
    placement = adaptive_legend_placement(7)
    assert placement["legend_loc"] == "upper left"
    assert placement["legend_ncol"] == 1
    assert placement["legend_bbox_to_anchor"] == (1.02, 1.0)
    assert placement["layout_rect"] == (0.0, 0.0, 0.85, 1.0)


def test_adaptive_legend_placement_honors_bottom_overrides():
    """The bottom offset/reserved-space params override the defaults."""
    placement = adaptive_legend_placement(2, bottom_anchor=(0.5, -0.18), bottom_rect_bottom=0.12)
    assert placement["legend_bbox_to_anchor"] == (0.5, -0.18)
    assert placement["layout_rect"] == (0.0, 0.12, 1.0, 1.0)


def test_style_axes_uses_single_axis_grid():
    """Cartesian charts should keep only the requested grid axis visible."""
    fig, ax = create_figure()
    ax.plot([2023, 2024], [3, 5])

    style_axes(ax, grid_axis="y")

    assert not any(line.get_visible() for line in ax.get_xgridlines())
    assert any(line.get_visible() for line in ax.get_ygridlines())
    assert not ax.spines["top"].get_visible()
    assert not ax.spines["right"].get_visible()

    plt.close(fig)
