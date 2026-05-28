"""Tests for the scatter-with-regression chart helper."""

from __future__ import annotations

import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg")

from hiero_analytics.plotting.scatter import plot_scatter_with_regression


def test_plot_scatter_with_regression_writes_chart_file(tmp_path):
    """Valid numeric data should produce a non-empty chart file."""
    scatter_df = pd.DataFrame(
        {
            "x": [1.0, 2.0, 3.0, 4.0, 5.0],
            "y": [2.1, 4.0, 5.8, 8.2, 9.7],
        }
    )
    output = tmp_path / "scatter_regression.png"

    plot_scatter_with_regression(
        scatter_df,
        x_col="x",
        y_col="y",
        title="Test Scatter",
        xlabel="X Axis",
        ylabel="Y Axis",
        output_path=output,
    )

    assert output.exists() and output.stat().st_size > 0


def test_plot_scatter_with_regression_raises_on_empty_dataframe(tmp_path):
    """An empty DataFrame should raise immediately."""
    empty_df = pd.DataFrame({"x": pd.Series(dtype=float), "y": pd.Series(dtype=float)})

    with pytest.raises(ValueError, match="DataFrame is empty"):
        plot_scatter_with_regression(
            empty_df,
            x_col="x",
            y_col="y",
            title="Empty",
            xlabel="X",
            ylabel="Y",
            output_path=tmp_path / "should_not_exist.png",
        )


def test_plot_scatter_with_regression_raises_on_all_na_data(tmp_path):
    """A DataFrame that becomes empty after dropping NA should raise."""
    na_df = pd.DataFrame(
        {
            "x": [np.nan, np.nan, np.nan],
            "y": [np.nan, np.nan, np.nan],
        }
    )

    with pytest.raises(ValueError, match="No valid data after dropping NA"):
        plot_scatter_with_regression(
            na_df,
            x_col="x",
            y_col="y",
            title="All NA",
            xlabel="X",
            ylabel="Y",
            output_path=tmp_path / "should_not_exist.png",
        )


def test_plot_scatter_with_regression_handles_single_data_point(tmp_path):
    """A single valid row should produce a chart (correlation set to NaN)."""
    single_df = pd.DataFrame(
        {
            "x": [3.0],
            "y": [7.0],
        }
    )
    output = tmp_path / "scatter_single.png"

    plot_scatter_with_regression(
        single_df,
        x_col="x",
        y_col="y",
        title="Single Point",
        xlabel="X",
        ylabel="Y",
        output_path=output,
    )

    assert output.exists() and output.stat().st_size > 0
