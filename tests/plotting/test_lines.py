"""Tests for line and stacked-area charts, including the datetime-axis handling."""

from __future__ import annotations

import matplotlib
import pandas as pd
import pytest

matplotlib.use("Agg")

from hiero_analytics.plotting.lines import plot_date_line, plot_stacked_area


def test_plot_stacked_area_writes_chart_file(tmp_path):
    """``plot_stacked_area`` should export a non-empty chart asset."""
    area_df = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-08", "2024-01-15"],
            "gfi": [2, 3, 4],
            "beginner": [0, 1, 1],
            "intermediate": [0, 1, 2],
            "advanced": [0, 0, 1],
        }
    )
    output = tmp_path / "difficulty_over_time.png"

    plot_stacked_area(
        area_df,
        x_col="date",
        stack_cols=["gfi", "beginner", "intermediate", "advanced"],
        labels=["Good First Issue", "Beginner", "Intermediate", "Advanced"],
        title="Open Issues by Difficulty Over Time",
        output_path=output,
        xlabel="Date",
        ylabel="Open issues",
    )

    assert output.exists() and output.stat().st_size > 0


def test_plot_date_line_writes_chart_with_datetime_x_axis(tmp_path):
    """``plot_date_line`` should preserve datetime axes (unlike ``plot_line``)."""
    monthly_df = pd.DataFrame(
        {
            "month": pd.to_datetime(["2025-09-01", "2025-10-01", "2025-11-01", "2025-12-01", "2026-01-01"]),
            "messages": [12, 30, 22, 41, 75],
        }
    )
    output = tmp_path / "monthly_line.png"

    plot_date_line(monthly_df, x_col="month", y_col="messages", title="Monthly traffic", output_path=output)

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

    plot_date_line(monthly_df, x_col="month", y_col="messages", title="Non-default index", output_path=output)

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

    plot_date_line(monthly_df, x_col="month", y_col="messages", title="All-zero series", output_path=output)

    assert output.exists() and output.stat().st_size > 0
    assert not any("singular" in str(w.message).lower() for w in recwarn)


def test_plot_date_line_raises_on_unparseable_dates(tmp_path):
    """Garbage date strings should fail loudly rather than silently produce a blank chart."""
    bad_df = pd.DataFrame({"month": ["not-a-date", "also-bad"], "messages": [1, 2]})

    with pytest.raises(ValueError, match="datetime"):
        plot_date_line(bad_df, x_col="month", y_col="messages", title="Broken dates", output_path=tmp_path / "b.png")


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
