"""Tests for the donut/pie chart helper: positive-total guard, legend, file export."""

from __future__ import annotations

import matplotlib
import pandas as pd
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt

import hiero_analytics.plotting.pie as pie_module
from hiero_analytics.plotting.pie import plot_pie


def test_plot_pie_writes_chart_file(tmp_path):
    """``plot_pie`` should export a non-empty chart asset."""
    pie_df = pd.DataFrame({"difficulty": ["Unknown", "Good First Issue", "Beginner"], "count": [7, 9, 4]})
    output = tmp_path / "difficulty_donut.png"

    plot_pie(pie_df, label_col="difficulty", value_col="count", title="Issue Difficulty", output_path=output)

    assert output.exists() and output.stat().st_size > 0


def test_plot_pie_rejects_non_positive_totals(tmp_path):
    """Pie charts should fail fast when there is no positive total to render."""
    pie_df = pd.DataFrame({"difficulty": ["Unknown", "Beginner"], "count": [0, 0]})

    with pytest.raises(ValueError, match="positive total"):
        plot_pie(
            pie_df,
            label_col="difficulty",
            value_col="count",
            title="Issue Difficulty Distribution",
            output_path=tmp_path / "difficulty_donut.png",
        )


def test_plot_pie_legend_and_center_label(monkeypatch, tmp_path):
    """The legend derives its title from the label column; slices sort by value."""
    pie_df = pd.DataFrame({"priority": ["Low", "High", "Medium"], "count": [3, 7, 5]})
    captured: dict[str, list[str] | str] = {}

    def capture_finalize(fig, ax, **kwargs):
        # The legend is created inside finalize_chart's shared path now, so the
        # stub captures the legend parameters the chart passes instead.
        captured["legend_title"] = kwargs["legend_title"]
        captured["legend_labels"] = list(kwargs["legend_labels"])
        captured["center_text"] = [text.get_text() for text in ax.texts]
        plt.close(fig)

    monkeypatch.setattr(pie_module, "finalize_chart", capture_finalize)

    pie_module.plot_pie(
        pie_df,
        label_col="priority",
        value_col="count",
        title="Issue Priority Distribution",
        output_path=tmp_path / "priority_donut.png",
        center_label="Open issues",
    )

    assert captured["legend_title"] == "Priority"  # humanized label column
    assert captured["legend_labels"][0].startswith("High")  # largest slice first
    assert "Open issues" in captured["center_text"]
