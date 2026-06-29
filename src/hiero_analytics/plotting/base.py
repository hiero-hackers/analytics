"""Common plotting helpers shared across all chart types."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.artist import Artist
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.legend import Legend

from hiero_analytics.config.charts import (
    CARD_BORDER_COLOR,
    DEFAULT_DPI,
    DEFAULT_FIGSIZE,
    FIGURE_BACKGROUND_COLOR,
    GRID_COLOR,
    GRID_LINE_WIDTH,
    LEGEND_BACKGROUND_COLOR,
    LEGEND_BOX_STYLE,
    LEGEND_EDGE_COLOR,
    MUTED_TEXT_COLOR,
    PLOT_BACKGROUND_COLOR,
    TEXT_COLOR,
    TITLE_COLOR,
)

from .style import apply_style


def _require_non_empty(df: pd.DataFrame) -> None:
    """Ensure the DataFrame is not empty."""
    if df.empty:
        raise ValueError("DataFrame is empty")


def _require_columns(df: pd.DataFrame, *columns: str) -> None:
    """Ensure required columns exist in the DataFrame."""
    missing = [col for col in columns if col not in df.columns]

    if missing:
        raise KeyError(f"Missing columns: {missing}")


def prepare_dataframe(df: pd.DataFrame, *cols: str) -> pd.DataFrame:
    """
    Validate and clean a dataframe for plotting.

    Ensures required columns exist, the dataframe is not empty,
    and removes rows with missing values in required columns.
    """
    _require_columns(df, *cols)
    _require_non_empty(df)

    data = df.dropna(subset=cols).copy()

    if data.empty:
        raise ValueError("No valid data available for plotting")

    return data


def adaptive_legend_placement(
    count: int,
    *,
    bottom_anchor: tuple[float, float] = (0.5, -0.14),
    bottom_rect_bottom: float = 0.14,
) -> dict[str, Any]:
    """Choose legend placement that adapts to the number of legend entries.

    With few entries (``<= 6``) the legend sits in a wide row beneath the plot;
    with many it moves to a single column on the right so labels do not
    overflow. Returns kwargs ready to splat into :func:`finalize_chart`.

    The bottom-legend offset and the layout space it reserves differ slightly
    between chart types, so they are parameters rather than hard-coded.
    """
    if count > 6:
        return {
            "legend_loc": "upper left",
            "legend_bbox_to_anchor": (1.02, 1.0),
            "legend_ncol": 1,
            "layout_rect": (0.0, 0.0, 0.85, 1.0),
        }
    return {
        "legend_loc": "lower center",
        "legend_bbox_to_anchor": bottom_anchor,
        "legend_ncol": min(count, 4),
        "layout_rect": (0.0, bottom_rect_bottom, 1.0, 1.0),
    }


def create_figure(
    figsize: tuple[float, float] = DEFAULT_FIGSIZE,
) -> tuple[Figure, Axes]:
    """Create and configure a new matplotlib figure."""
    apply_style()

    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(FIGURE_BACKGROUND_COLOR)
    ax.set_facecolor(PLOT_BACKGROUND_COLOR)

    return fig, ax


def style_axes(ax: Axes, *, grid_axis: str | None = "y") -> None:
    """Apply a clean card-like axis treatment inspired by shadcn charts."""
    # Treat the plotting region like a chart card inside the figure canvas.
    ax.set_facecolor(PLOT_BACKGROUND_COLOR)
    ax.set_axisbelow(True)
    ax.patch.set_edgecolor(CARD_BORDER_COLOR)
    ax.patch.set_linewidth(1.0)

    if grid_axis is None:
        # Non-cartesian charts such as donuts should read as clean summaries
        # without axis furniture.
        ax.grid(False)
        ax.tick_params(
            axis="both",
            which="both",
            bottom=False,
            left=False,
            labelbottom=False,
            labelleft=False,
        )
        for spine in ax.spines.values():
            spine.set_visible(False)
        return

    # Only show the grid on the informative axis so the chart stays readable.
    ax.grid(False)
    ax.grid(axis=grid_axis, color=GRID_COLOR, linewidth=GRID_LINE_WIDTH)

    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)

    ax.tick_params(axis="x", colors=MUTED_TEXT_COLOR, pad=8)
    ax.tick_params(axis="y", colors=MUTED_TEXT_COLOR, pad=8)
    ax.xaxis.label.set_color(MUTED_TEXT_COLOR)
    ax.yaxis.label.set_color(MUTED_TEXT_COLOR)
    ax.title.set_color(TITLE_COLOR)


def style_legend(legend: Legend | None) -> None:
    """Make legends feel closer to chart card UI than default matplotlib."""
    if legend is None:
        return

    frame = legend.get_frame()
    frame.set_facecolor(LEGEND_BACKGROUND_COLOR)
    frame.set_edgecolor(LEGEND_EDGE_COLOR)
    frame.set_linewidth(0.9)

    with suppress(AttributeError):
        frame.set_boxstyle(LEGEND_BOX_STYLE)

    title = legend.get_title()
    if title.get_text():
        title.set_color(TITLE_COLOR)

    for text in legend.get_texts():
        text.set_color(TEXT_COLOR)

    if legend.axes is not None:
        for spine in legend.axes.spines.values():
            spine.set_edgecolor(CARD_BORDER_COLOR)


def finalize_chart(
    fig: Figure,
    ax: Axes,
    title: str,
    xlabel: str,
    ylabel: str,
    output_path: Path,
    legend: bool = False,
    rotate_x: int | None = None,
    grid_axis: str | None = "y",
    legend_title: str | None = None,
    legend_handles: Sequence[Artist] | None = None,
    legend_labels: Sequence[str] | None = None,
    legend_loc: str = "best",
    legend_bbox_to_anchor: tuple[float, float] | None = None,
    legend_ncol: int = 1,
    legend_kwargs: dict[str, Any] | None = None,
    layout_rect: tuple[float, float, float, float] | None = None,
) -> None:
    """Finalize and save a chart."""
    # Titles are left-aligned to feel more like dashboard/report headings.
    ax.set_title(title, loc="left")
    style_axes(ax, grid_axis=grid_axis)

    if xlabel:
        ax.set_xlabel(xlabel)

    if ylabel:
        ax.set_ylabel(ylabel)

    if rotate_x is not None:
        for label in ax.get_xticklabels():
            label.set_rotation(rotate_x)
            label.set_ha("right")
            label.set_rotation_mode("anchor")

    if legend:
        # The legend can be positioned outside the plotting region so it uses
        # whitespace rather than covering data.
        legend_artist = ax.legend(
            handles=legend_handles,
            labels=legend_labels,
            title=legend_title,
            frameon=True,
            loc=legend_loc,
            bbox_to_anchor=legend_bbox_to_anchor,
            ncol=legend_ncol,
            **(legend_kwargs or {}),
        )
        style_legend(legend_artist)

    # Reserve optional outer space for legends or header elements before export.
    fig.tight_layout(rect=layout_rect)

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save chart
    fig.savefig(output_path, dpi=DEFAULT_DPI, bbox_inches="tight")

    # Close figure to prevent memory leaks during batch runs
    plt.close(fig)
