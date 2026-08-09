"""Tests for the scatter-with-regression chart helper."""

from __future__ import annotations

import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg")

from hiero_analytics.plotting.scatter import plot_release_timeline, plot_scatter_with_regression


def test_plot_release_timeline_writes_chart_file(tmp_path):
    """A normal set of releases across a few repos produces a non-empty chart file."""
    df = pd.DataFrame(
        {
            "repo": ["org/a", "org/a", "org/b", "org/c"],
            "published_at": pd.to_datetime(["2026-01-01", "2026-03-01", "2026-02-01", "2026-01-15"], utc=True),
            "is_prerelease": [False, True, False, False],
        }
    )
    output = tmp_path / "release_timeline.png"

    plot_release_timeline(df, title="Release Timeline", output_path=output)

    assert output.exists() and output.stat().st_size > 0


def test_plot_release_timeline_raises_on_empty_dataframe(tmp_path):
    """An empty DataFrame should raise immediately, matching the other chart helpers."""
    empty_df = pd.DataFrame({"repo": pd.Series(dtype=str), "published_at": pd.Series(dtype="datetime64[ns, UTC]")})

    with pytest.raises(ValueError, match="DataFrame is empty"):
        plot_release_timeline(empty_df, title="Empty", output_path=tmp_path / "should_not_exist.png")


def test_plot_release_timeline_raises_on_missing_column(tmp_path):
    """A missing required column is reported clearly, not as a raw pandas error."""
    df = pd.DataFrame({"repo": ["org/a"]})  # no "published_at" column

    with pytest.raises(KeyError, match="Missing columns"):
        plot_release_timeline(df, title="Missing", output_path=tmp_path / "should_not_exist.png")


def test_plot_release_timeline_handles_a_single_repo_with_many_releases(tmp_path):
    """A high-cadence single repo (the overplotting stress case from #331) still renders."""
    df = pd.DataFrame(
        {
            "repo": ["org/busy"] * 50,
            "published_at": pd.date_range("2025-02-01", periods=50, freq="11D", tz="UTC"),
            "is_prerelease": [i % 5 == 0 for i in range(50)],
        }
    )
    output = tmp_path / "release_timeline_busy.png"

    plot_release_timeline(df, title="Busy repo", output_path=output)

    assert output.exists() and output.stat().st_size > 0


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


def test_plot_scatter_with_regression_raises_on_missing_column(tmp_path):
    """A missing required column is reported clearly, not as a raw pandas error."""
    df = pd.DataFrame({"x": [1.0, 2.0]})  # no "y" column

    with pytest.raises(KeyError, match="Missing columns"):
        plot_scatter_with_regression(
            df,
            x_col="x",
            y_col="y",
            title="Missing",
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

    with pytest.raises(ValueError, match="No valid data available for plotting"):
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
