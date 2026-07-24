"""Reusable plotting helpers shared across chart implementations."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
from matplotlib.axes import Axes

from hiero_analytics.config.charts import (
    ANNOTATION_FONT_SIZE,
    BADGE_FONT_SIZE,
    CARD_BORDER_COLOR,
    CARD_EDGE_LINE_WIDTH,
    ENDPOINT_LABEL_BOX_STYLE,
    PLOT_BACKGROUND_COLOR,
    PRIMARY_PALETTE,
)


def build_palette(size: int, palette: Sequence[str] | None = None) -> list[str]:
    """Repeat a base palette so charts can style an arbitrary number of series."""
    base_palette = tuple(palette or PRIMARY_PALETTE)
    if not base_palette:
        raise ValueError("Palette must contain at least one color")

    return [base_palette[index % len(base_palette)] for index in range(size)]


def format_chart_value(value: float) -> str:
    """Format chart values without noisy trailing decimals."""
    return f"{int(value):,}" if float(value).is_integer() else f"{value:,.1f}"


def is_numeric_or_datetime(series: pd.Series) -> bool:
    """Return whether a series should keep a quantitative axis."""
    return bool(
        pd.api.types.is_numeric_dtype(series)
        or pd.api.types.is_datetime64_any_dtype(series)
        or isinstance(series.dtype, pd.PeriodDtype)
    )


def styled_text_badge(
    ax: Axes,
    *,
    x: float,
    y: float,
    text: str,
    color: str,
) -> None:
    """Render axes-fraction text in the shared white-card pill styling."""
    ax.text(
        x,
        y,
        text,
        transform=ax.transAxes,
        fontsize=ANNOTATION_FONT_SIZE,
        color=color,
        va="top",
        bbox={
            "boxstyle": ENDPOINT_LABEL_BOX_STYLE,
            "fc": PLOT_BACKGROUND_COLOR,
            "ec": CARD_BORDER_COLOR,
            "lw": CARD_EDGE_LINE_WIDTH,
        },
        zorder=5,
    )


def annotate_endpoint_badge(
    ax: Axes,
    *,
    x: float,
    y: float,
    text: str,
    color: str,
    y_offset: int,
    x_offset: int = 10,
) -> None:
    """Label a series endpoint with a lightweight pill."""
    ax.annotate(
        text,
        xy=(x, y),
        xytext=(x_offset, y_offset),
        textcoords="offset points",
        ha="left",
        va="center",
        fontsize=BADGE_FONT_SIZE,
        color=color,
        bbox={
            "boxstyle": ENDPOINT_LABEL_BOX_STYLE,
            "fc": PLOT_BACKGROUND_COLOR,
            "ec": CARD_BORDER_COLOR,
            "lw": CARD_EDGE_LINE_WIDTH,
        },
        zorder=5,
    )
