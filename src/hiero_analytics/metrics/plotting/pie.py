from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path

from .base import create_figure, finalize_chart


def plot_pie(
    df: pd.DataFrame,
    label_col: str,
    value_col: str,
    title: str,
    output_path: Path,
) -> None:

    if df.empty:
        return

    create_figure()

    plt.pie(
        df[value_col],
        labels=df[label_col],
        autopct="%1.1f%%",
        startangle=90,
    )

    plt.axis("equal")

    finalize_chart(
        title=title,
        xlabel="",
        ylabel="",
        output_path=output_path,
    )