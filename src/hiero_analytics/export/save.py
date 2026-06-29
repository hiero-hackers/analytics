from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pandas as pd


def save_dataframe(
    df: pd.DataFrame,
    path: Path,
) -> None:
    """
    Save a dataframe to a CSV file.

    Args:
        df: The dataframe to save.
        path: The path where the CSV file will be saved.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def plot_and_save(
    df: pd.DataFrame,
    plot_fn: Callable[..., None],
    *,
    output_path: Path,
    csv_path: Path | None = None,
    **plot_kwargs: object,
) -> None:
    """
    Render a chart and optionally save its source data, skipping empty frames.

    Collapses the ``if not df.empty: plot_x(...); save_dataframe(...)`` block
    repeated across runners. ``df`` is passed positionally so any chart helper
    works regardless of its first parameter's name (``df``/``channels``/...).

    Args:
        df: The data to plot (and save). Nothing happens if it is empty.
        plot_fn: A chart helper taking the frame positionally plus ``output_path``.
        output_path: Where the chart image is written.
        csv_path: If given, the frame is also written there as CSV.
        **plot_kwargs: Extra keyword arguments forwarded to ``plot_fn``.
    """
    if df.empty:
        return

    plot_fn(df, output_path=output_path, **plot_kwargs)

    if csv_path is not None:
        save_dataframe(df, csv_path)