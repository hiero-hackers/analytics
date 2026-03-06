"""
Applies consistent styling to matplotlib charts for analytics visualizations.
Pulls the style configuration from src/hiero_analytics/config/charts.py to ensure all charts have a cohesive look and feel.
"""
from __future__ import annotations

import matplotlib.pyplot as plt

from hiero_analytics.config.charts import (
    DEFAULT_STYLE,
    DEFAULT_FIGSIZE,
    TITLE_FONT_SIZE,
    LABEL_FONT_SIZE,
    TICK_FONT_SIZE,
    LEGEND_FONT_SIZE,
    GRID_ENABLED,
    GRID_ALPHA,
    GRID_STYLE,
)


def apply_style() -> None:
    """
    Apply consistent matplotlib styling for analytics charts.
    """

    plt.style.use(DEFAULT_STYLE)

    plt.rcParams.update(
        {
            "figure.figsize": DEFAULT_FIGSIZE,
            "figure.autolayout": True,
            "axes.titlesize": TITLE_FONT_SIZE,
            "axes.labelsize": LABEL_FONT_SIZE,
            "xtick.labelsize": TICK_FONT_SIZE,
            "ytick.labelsize": TICK_FONT_SIZE,
            "legend.fontsize": LEGEND_FONT_SIZE,
            "axes.grid": GRID_ENABLED,
            "grid.alpha": GRID_ALPHA,
            "grid.linestyle": GRID_STYLE,
        }
    )