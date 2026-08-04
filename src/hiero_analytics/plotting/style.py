"""
Centralized matplotlib styling for analytics charts.

This module applies a consistent visual style across all charts generated
by the analytics system. Style configuration values are sourced from
`hiero_analytics.config.charts`.

It also owns the provenance footer every figure carries, so the stamp is styled
in the same place as the rest of the chart furniture rather than at each of the
dozen call sites that render one.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from hiero_analytics.config.charts import (
    AXIS_LINE_COLOR,
    DEFAULT_FIGSIZE,
    DEFAULT_STYLE,
    FIGURE_BACKGROUND_COLOR,
    FONT_FAMILY,
    FOOTER_ALPHA,
    FOOTER_FONT_SIZE,
    FOOTER_X,
    FOOTER_Y,
    GRID_ALPHA,
    GRID_COLOR,
    GRID_ENABLED,
    GRID_LINE_WIDTH,
    GRID_STYLE,
    LABEL_FONT_SIZE,
    LEGEND_BACKGROUND_COLOR,
    LEGEND_EDGE_COLOR,
    LEGEND_FONT_SIZE,
    MUTED_TEXT_COLOR,
    PLOT_BACKGROUND_COLOR,
    TEXT_COLOR,
    TICK_FONT_SIZE,
    TITLE_COLOR,
    TITLE_FONT_SIZE,
)
from hiero_analytics.provenance import resolve_provenance

logger = logging.getLogger(__name__)

# Prevent applying style multiple times
_STYLE_APPLIED = False


def apply_style() -> None:
    """
    Apply consistent matplotlib styling for analytics charts.

    This function configures global matplotlib style parameters to ensure
    consistent appearance across all generated charts.

    It is safe to call multiple times; the style will only be applied once.
    """
    global _STYLE_APPLIED

    if _STYLE_APPLIED:
        return

    # Start from matplotlib's default theme and then layer our shared analytics
    # styling on top so every chart export looks consistent.
    plt.style.use(DEFAULT_STYLE)

    plt.rcParams.update(
        {
            "figure.figsize": DEFAULT_FIGSIZE,
            "figure.facecolor": FIGURE_BACKGROUND_COLOR,
            "savefig.facecolor": FIGURE_BACKGROUND_COLOR,
            "savefig.transparent": False,
            "axes.facecolor": PLOT_BACKGROUND_COLOR,
            "axes.titlesize": TITLE_FONT_SIZE,
            "axes.titleweight": 700,
            "axes.titlecolor": TITLE_COLOR,
            "axes.titlepad": 18,
            "axes.labelsize": LABEL_FONT_SIZE,
            "axes.labelcolor": MUTED_TEXT_COLOR,
            "axes.edgecolor": AXIS_LINE_COLOR,
            "axes.linewidth": 0.9,
            "axes.axisbelow": True,
            "xtick.labelsize": TICK_FONT_SIZE,
            "ytick.labelsize": TICK_FONT_SIZE,
            "xtick.color": MUTED_TEXT_COLOR,
            "ytick.color": MUTED_TEXT_COLOR,
            "xtick.major.size": 0,
            "ytick.major.size": 0,
            "text.color": TEXT_COLOR,
            "font.family": FONT_FAMILY,
            "legend.fontsize": LEGEND_FONT_SIZE,
            "legend.facecolor": LEGEND_BACKGROUND_COLOR,
            "legend.edgecolor": LEGEND_EDGE_COLOR,
            "legend.framealpha": 1.0,
            "legend.fancybox": True,
            "axes.grid": GRID_ENABLED,
            "grid.alpha": GRID_ALPHA,
            "grid.linestyle": GRID_STYLE,
            "grid.color": GRID_COLOR,
            "grid.linewidth": GRID_LINE_WIDTH,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )

    _STYLE_APPLIED = True


def draw_provenance_footer(fig: Figure, *, record_count: int | Mapping[str, int] | None = None) -> None:
    """Stamp ``fig`` with the data watermark, code revision, and row count.

    A chart that leaves this module is a standalone PNG: it gets embedded in the
    dashboard, pasted into issues, and dropped into slide decks, long outliving
    the five-day refresh that produced it. The footer is what lets a reader come
    back to one later and say which dataset snapshot and which revision drew it.

    Never raises. An unstamped chart is a small loss; a provenance lookup that
    takes down a chart — or a whole multi-hour pipeline run — is a large one, so
    any failure degrades to no footer and a debug log.
    """
    try:
        text = resolve_provenance().footer(record_count)
        if not text:
            return
        fig.text(
            FOOTER_X,
            FOOTER_Y,
            text,
            ha="right",
            va="bottom",
            fontsize=FOOTER_FONT_SIZE,
            color=MUTED_TEXT_COLOR,
            alpha=FOOTER_ALPHA,
        )
    except Exception:  # noqa: BLE001 - a cosmetic stamp must never fail a render
        logger.debug("Could not stamp provenance footer", exc_info=True)
