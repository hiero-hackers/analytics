"""Tests for plotting primitives and shared chart styling."""

from __future__ import annotations

import matplotlib
import pandas as pd
import pytest
from matplotlib.patches import FancyBboxPatch

matplotlib.use("Agg")

import matplotlib.pyplot as plt

import hiero_analytics.plotting.pie as pie_module
from hiero_analytics.plotting.bars import _compute_annotation_padding, _round_bar_patches, plot_bar
from hiero_analytics.plotting.base import (
    adaptive_legend_placement,
    create_figure,
    style_axes,
)
from hiero_analytics.plotting.lines import plot_date_line, plot_multiline, plot_stacked_area
from hiero_analytics.plotting.pie import plot_pie


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
    placement = adaptive_legend_placement(
        2, bottom_anchor=(0.5, -0.18), bottom_rect_bottom=0.12
    )
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


def test_plotters_write_chart_files(tmp_path):
    """The main plotting helpers should export non-empty chart assets."""
    bar_df = pd.DataFrame(
        {
            "repo": ["mirror-node", "sdk-python", "solo"],
            "count": [24, 18, 12],
        }
    )
    line_df = pd.DataFrame(
        {
            "year": [2023, 2023, 2024, 2024],
            "count": [8, 3, 12, 5],
            "state": ["open", "closed", "open", "closed"],
        }
    )
    pie_df = pd.DataFrame(
        {
            "difficulty": ["Unknown", "Good First Issue", "Beginner"],
            "count": [7, 9, 4],
        }
    )
    area_df = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-08", "2024-01-15"],
            "gfi": [2, 3, 4],
            "beginner": [0, 1, 1],
            "intermediate": [0, 1, 2],
            "advanced": [0, 0, 1],
        }
    )

    bar_output = tmp_path / "difficulty_by_repo.png"
    line_output = tmp_path / "gfi_state_line.png"
    pie_output = tmp_path / "difficulty_donut.png"
    area_output = tmp_path / "difficulty_over_time.png"

    plot_bar(
        bar_df,
        x_col="repo",
        y_col="count",
        title="Issues by Repository",
        output_path=bar_output,
        rotate_x=30,
    )
    plot_multiline(
        line_df,
        x_col="year",
        y_col="count",
        group_col="state",
        title="Good First Issues by State",
        output_path=line_output,
    )
    plot_pie(
        pie_df,
        label_col="difficulty",
        value_col="count",
        title="Issue Difficulty Distribution",
        output_path=pie_output,
    )
    plot_stacked_area(
        area_df,
        x_col="date",
        stack_cols=["gfi", "beginner", "intermediate", "advanced"],
        labels=["Good First Issue", "Beginner", "Intermediate", "Advanced"],
        title="Open Issues by Difficulty Over Time",
        output_path=area_output,
        xlabel="Date",
        ylabel="Open issues",
    )

    assert bar_output.exists() and bar_output.stat().st_size > 0
    assert line_output.exists() and line_output.stat().st_size > 0
    assert pie_output.exists() and pie_output.stat().st_size > 0
    assert area_output.exists() and area_output.stat().st_size > 0


def test_plot_date_line_writes_chart_with_datetime_x_axis(tmp_path):
    """``plot_date_line`` should preserve datetime axes (unlike ``plot_line``)."""
    monthly_df = pd.DataFrame(
        {
            "month": pd.to_datetime(
                ["2025-09-01", "2025-10-01", "2025-11-01", "2025-12-01", "2026-01-01"]
            ),
            "messages": [12, 30, 22, 41, 75],
        }
    )
    output = tmp_path / "monthly_line.png"

    plot_date_line(
        monthly_df,
        x_col="month",
        y_col="messages",
        title="Monthly traffic",
        output_path=output,
    )

    assert output.exists() and output.stat().st_size > 0


def test_plot_date_line_handles_non_default_index(tmp_path):
    """``idxmax`` returns a label, not an int — non-default indexes must work."""
    monthly_df = pd.DataFrame(
        {
            "month": pd.to_datetime(["2025-09-01", "2025-10-01", "2025-11-01"]),
            "messages": [5, 30, 10],
        },
        index=["a", "b", "c"],  # Non-RangeIndex would break an ``int(idxmax())`` cast.
    )
    output = tmp_path / "non_default_index.png"

    plot_date_line(
        monthly_df,
        x_col="month",
        y_col="messages",
        title="Non-default index",
        output_path=output,
    )

    assert output.exists() and output.stat().st_size > 0


def test_plot_date_line_handles_all_zero_series(tmp_path, recwarn):
    """All-zero y values must not trigger matplotlib's singular-limits warning."""
    monthly_df = pd.DataFrame(
        {
            "month": pd.to_datetime(["2025-09-01", "2025-10-01"]),
            "messages": [0, 0],
        }
    )
    output = tmp_path / "all_zero.png"

    plot_date_line(
        monthly_df,
        x_col="month",
        y_col="messages",
        title="All-zero series",
        output_path=output,
    )

    assert output.exists() and output.stat().st_size > 0
    assert not any("singular" in str(w.message).lower() for w in recwarn)


def test_plot_date_line_raises_on_unparseable_dates(tmp_path):
    """Garbage date strings should fail loudly rather than silently produce a blank chart."""
    bad_df = pd.DataFrame({"month": ["not-a-date", "also-bad"], "messages": [1, 2]})

    with pytest.raises(ValueError, match="datetime"):
        plot_date_line(
            bad_df,
            x_col="month",
            y_col="messages",
            title="Broken dates",
            output_path=tmp_path / "broken.png",
        )


def test_plot_date_line_respects_annotation_toggle(tmp_path):
    """Disabling annotations should still produce a chart (no crashes)."""
    monthly_df = pd.DataFrame(
        {
            "month": pd.to_datetime(["2025-09-01", "2025-10-01"]),
            "messages": [10, 20],
        }
    )
    output = tmp_path / "no_annotations.png"

    plot_date_line(
        monthly_df,
        x_col="month",
        y_col="messages",
        title="No callouts",
        output_path=output,
        annotate_peak_and_latest=False,
    )

    assert output.exists() and output.stat().st_size > 0


def test_plot_pie_rejects_non_positive_totals(tmp_path):
    """Pie charts should fail fast when there is no positive total to render."""
    pie_df = pd.DataFrame(
        {
            "difficulty": ["Unknown", "Beginner"],
            "count": [0, 0],
        }
    )

    with pytest.raises(ValueError, match="positive total"):
        plot_pie(
            pie_df,
            label_col="difficulty",
            value_col="count",
            title="Issue Difficulty Distribution",
            output_path=tmp_path / "difficulty_donut.png",
        )


def test_plot_pie_accepts_custom_metadata(monkeypatch, tmp_path):
    """Pie charts should keep domain labels configurable at the call site."""
    pie_df = pd.DataFrame(
        {
            "priority": ["Low", "High", "Medium"],
            "count": [3, 7, 5],
        }
    )
    captured: dict[str, list[str] | str] = {}

    def capture_finalize(fig, ax, **_kwargs):
        legend = ax.get_legend()
        assert legend is not None
        captured["legend_title"] = legend.get_title().get_text()
        captured["legend_labels"] = [text.get_text() for text in legend.get_texts()]
        captured["center_text"] = [text.get_text() for text in ax.texts]
        plt.close(fig)

    monkeypatch.setattr(pie_module, "finalize_chart", capture_finalize)

    pie_module.plot_pie(
        pie_df,
        label_col="priority",
        value_col="count",
        title="Issue Priority Distribution",
        output_path=tmp_path / "priority_donut.png",
        label_order=["High", "Medium", "Low"],
        legend_title="Priority",
        center_label="Open issues",
    )

    assert captured["legend_title"] == "Priority"
    assert captured["legend_labels"][0].startswith("High")
    assert "Open issues" in captured["center_text"]
