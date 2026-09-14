"""
Centralized matplotlib styling for analytics charts.

This module applies a consistent visual style across all charts generated
by the analytics system. Style configuration values are sourced from
`hiero_analytics.config.charts`.

It also owns the provenance footer every figure carries, so the stamp is styled
in the same place as the rest of the chart furniture rather than at each of the
dozen call sites that render one, and the registration of the vendored Inter
faces the web dashboard shares.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.figure import Figure

from hiero_analytics.config.charts import (
    AXIS_LINE_COLOR,
    DEFAULT_FIGSIZE,
    DEFAULT_STYLE,
    FIGURE_BACKGROUND_COLOR,
    FONT_FALLBACKS,
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
)
from hiero_analytics.provenance import resolve_provenance

logger = logging.getLogger(__name__)

# Prevent applying style multiple times
_STYLE_APPLIED = False

# The Inter faces vendored beside this module (see `config.charts.FONT_FAMILY`).
_FONT_DIR = Path(__file__).parent / "fonts"


def _register_bundled_fonts() -> None:
    """Make the vendored Inter faces resolvable by ``FONT_FAMILY``.

    matplotlib only draws with fonts its font manager knows about, and it looks
    at system directories, not at ours — so the shipped TTFs have to be handed
    to it explicitly. Each face registers under family ``Inter`` with its own
    weight, which is what lets ``fontweight="semibold"`` pick SemiBold while
    body text stays Regular.

    Never raises. A chart set in the fallback typeface is a cosmetic
    regression; a pipeline that dies because a font file is missing from an
    install is not, so any failure degrades to ``FONT_FALLBACKS``.
    """
    try:
        for path in sorted(_FONT_DIR.glob("*.ttf")):
            font_manager.fontManager.addfont(str(path))
    except Exception:  # noqa: BLE001 - typography must never fail a render
        logger.debug("Could not register bundled fonts from %s", _FONT_DIR, exc_info=True)


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

    # Must precede the rcParams update: the font stack below names Inter, which
    # only resolves once the bundled faces are registered.
    _register_bundled_fonts()

    plt.rcParams.update(
        {
            "figure.figsize": DEFAULT_FIGSIZE,
            "figure.facecolor": FIGURE_BACKGROUND_COLOR,
            "savefig.facecolor": FIGURE_BACKGROUND_COLOR,
            "savefig.transparent": False,
            "axes.facecolor": PLOT_BACKGROUND_COLOR,
            # No axes-title params: charts are rendered untitled on purpose. The
            # dashboard captions every figure from the spec, so a baked-in title
            # printed the same string twice; see `base.finalize_chart`.
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
            "font.family": "sans-serif",
            "font.sans-serif": [FONT_FAMILY, *FONT_FALLBACKS],
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
