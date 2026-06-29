"""Tests for the plot_and_save output helper."""

import pandas as pd

from hiero_analytics.export.save import plot_and_save


def _recorder(calls):
    """Build a fake plot_fn that records each call's (df, output_path, kwargs)."""

    def record(df, output_path, **kwargs):
        calls.append((df, output_path, kwargs))

    return record


def test_plot_and_save_skips_empty_frame(tmp_path):
    """An empty frame plots nothing and writes nothing."""
    calls = []
    plot_and_save(
        pd.DataFrame(columns=["a"]),
        _recorder(calls),
        output_path=tmp_path / "chart.png",
        csv_path=tmp_path / "data.csv",
    )
    assert calls == []
    assert not (tmp_path / "data.csv").exists()


def test_plot_and_save_passes_df_positionally_and_forwards_kwargs(tmp_path):
    """The frame is passed positionally; output_path and extra kwargs forwarded."""
    calls = []
    df = pd.DataFrame({"a": [1, 2]})

    plot_and_save(df, _recorder(calls), output_path=tmp_path / "c.png", x_col="a", title="T")

    assert len(calls) == 1
    seen_df, seen_path, seen_kwargs = calls[0]
    assert seen_df is df
    assert seen_path == tmp_path / "c.png"
    assert seen_kwargs == {"x_col": "a", "title": "T"}


def test_plot_and_save_writes_csv_only_when_path_given(tmp_path):
    """csv_path is optional; the CSV is written only when provided."""
    calls = []
    df = pd.DataFrame({"a": [1]})

    plot_and_save(df, _recorder(calls), output_path=tmp_path / "c.png")
    assert not list(tmp_path.glob("*.csv"))

    plot_and_save(
        df, _recorder(calls), output_path=tmp_path / "c.png", csv_path=tmp_path / "d.csv"
    )
    assert (tmp_path / "d.csv").exists()
