from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path

from .base import create_figure, finalize_chart


def plot_stacked_bar(
    df: pd.DataFrame,
    x_col: str,
    stack_cols: list[str],
    labels: list[str],
    title: str,
    output_path: Path,
    rotate_x: int | None = None,
) -> None:
    """
    Plot stacked bar chart.
    """

    if df.empty:
        raise ValueError("DataFrame is empty")

    create_figure()

    bottom = None

    for col, label in zip(stack_cols, labels):

        plt.bar(
            df[x_col],
            df[col],
            bottom=bottom,
            label=label,
        )

        if bottom is None:
            bottom = df[col]
        else:
            bottom = bottom + df[col]

    finalize_chart(
        title=title,
        xlabel=x_col,
        ylabel="count",
        output_path=output_path,
        legend=True,
        rotate_x=rotate_x,
    )