"""Scatter plot with linear regression for the analytics design system."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from hiero_analytics.config.charts import (
    ANNOTATION_FONT_SIZE,
    MUTED_TEXT_COLOR,
    PRIMARY_PALETTE,
    TITLE_COLOR,
)
from hiero_analytics.plotting.base import (
    figure_context,
    finalize_chart,
    prepare_dataframe,
)
from hiero_analytics.plotting.primitives import styled_text_badge


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
    # Regression (needs at least two points — a single point cannot determine
    # a line, and an unguarded polyfit warns "poorly conditioned")
    # -------------------------
    has_regression = len(df) > 1
    if has_regression:
        slope, intercept = np.polyfit(x, y, 1)
        y_pred = slope * x + intercept
        r = np.corrcoef(x, y)[0, 1]

        # sort for clean line rendering
        order = np.argsort(x)
        x_sorted = x.iloc[order]
        y_pred_sorted = y_pred.iloc[order]

    # -------------------------
    # Plot
    # -------------------------
    with figure_context() as (fig, ax):
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

        if has_regression:
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
            styled_text_badge(ax, x=0.02, y=0.96, text=f"Slope {slope:.2f}", color=TITLE_COLOR)

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
