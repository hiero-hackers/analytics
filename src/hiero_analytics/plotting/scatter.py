from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

from hiero_analytics.config.charts import (
    PRIMARY_PALETTE,
    ANNOTATION_FONT_SIZE,
    TITLE_COLOR,
    MUTED_TEXT_COLOR,
    CARD_BORDER_COLOR,
    PLOT_BACKGROUND_COLOR,
)
from hiero_analytics.plotting.base import (
    create_figure,
    finalize_chart,
    prepare_dataframe,
)


def plot_scatter_with_regression(
    df: pd.DataFrame,
    *,
    x_col: str,
    y_col: str,
    title: str,
    xlabel: str,
    ylabel: str,
    output_path: Path,
) -> None:
    """
    Standardized scatter + regression chart.

    Features:
    - Clean scatter styling
    - Sorted regression line
    - Slope + correlation annotation
    - Consistent design system integration
    """

    # -------------------------
    # Prepare data (shared validation: required columns, non-empty, drop NA)
    # -------------------------
    df = prepare_dataframe(df, x_col, y_col)

    x = df[x_col].astype(float)
    y = df[y_col].astype(float)

    # -------------------------
    # Regression
    # -------------------------
    slope, intercept = np.polyfit(x, y, 1)
    y_pred = slope * x + intercept

    # correlation (guard small samples)
    r = np.corrcoef(x, y)[0, 1] if len(df) > 1 else np.nan

    # sort for clean line rendering
    order = np.argsort(x)
    x_sorted = x.iloc[order]
    y_pred_sorted = y_pred.iloc[order]

    # -------------------------
    # Plot
    # -------------------------
    fig, ax = create_figure()

    # Scatter
    ax.scatter(
        x,
        y,
        color=PRIMARY_PALETTE[2],
        alpha=0.55,
        s=38,
        edgecolors="none",
        zorder=3,
    )

    # Regression line
    ax.plot(
        x_sorted,
        y_pred_sorted,
        color=PRIMARY_PALETTE[0],
        linewidth=2.4,
        zorder=4,
    )

    # -------------------------
    # Annotations (styled)
    # -------------------------
    ax.text(
        0.02,
        0.96,
        f"Slope {slope:.2f}",
        transform=ax.transAxes,
        fontsize=ANNOTATION_FONT_SIZE,
        color=TITLE_COLOR,
        va="top",
        bbox={
            "boxstyle": "round,pad=0.28,rounding_size=0.8",
            "fc": PLOT_BACKGROUND_COLOR,
            "ec": CARD_BORDER_COLOR,
            "lw": 0.9,
        },
        zorder=5,
    )

    if not np.isnan(r):
        ax.text(
            0.02,
            0.88,
            f"r = {r:.2f}",
            transform=ax.transAxes,
            fontsize=ANNOTATION_FONT_SIZE,
            color=MUTED_TEXT_COLOR,
            va="top",
            zorder=5,
        )

    # -------------------------
    # Layout polish
    # -------------------------
    ax.margins(x=0.05, y=0.08)
    ax.set_ylim(bottom=0)

    # -------------------------
    # Finalize
    # -------------------------
    finalize_chart(
        fig=fig,
        ax=ax,
        title=title,
        xlabel=xlabel,
        ylabel=ylabel,
        output_path=output_path,
        legend=False,
        grid_axis="both",
    )