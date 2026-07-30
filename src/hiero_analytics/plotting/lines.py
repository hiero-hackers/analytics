"""Line chart primitives styled to match the shared analytics theme."""

from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.ticker as ticker
import pandas as pd
from matplotlib.patches import Patch

from hiero_analytics.config.charts import (
    ANNOTATION_FONT_SIZE,
    CARD_EDGE_LINE_WIDTH,
    ENDPOINT_LABEL_BOX_STYLE,
    FIGURE_BACKGROUND_COLOR,
    FONT_WEIGHT_SEMIBOLD,
    LEGEND_EDGE_COLOR,
    LINE_FILL_ALPHA,
    LINE_MARKER_EDGE_WIDTH,
    LINE_MARKER_SIZE,
    LINE_WIDTH,
    PLOT_BACKGROUND_COLOR,
    PRIMARY_PALETTE,
    TITLE_COLOR,
)

from .base import (
    figure_context,
    finalize_chart,
    prepare_dataframe,
)
from .primitives import annotate_endpoint_badge, build_palette, format_chart_value, is_numeric_or_datetime

# Headroom multiplier on the y-axis so badge annotations have room above the
# peak marker without overlapping the chart frame.
DATE_LINE_Y_HEADROOM = 1.25
DATE_LINE_X_MARGIN = 0.02
DATE_LINE_Y_MARGIN = 0.18
DATE_LINE_LABEL_OFFSET_Y = 14
# The total series reads as the headline trend, so it draws slightly heavier.
TOTAL_LINE_WIDTH = 3.0
SERIES_LINE_WIDTH = 2.4
STACKED_AREA_ALPHA = 0.96


def _style_numeric_line_axes(ax, x_min: float, x_max: float) -> None:
    """Integer ticks on both axes plus the shared numeric-line framing."""
    ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax.set_ylim(bottom=0)
    ax.set_xlim(x_min - 0.15, x_max + 0.45)
    ax.margins(x=0.03, y=0.16)


def _draw_series_line(ax, x, y, color: str, *, label: str | None = None, linewidth: float = LINE_WIDTH) -> None:
    """One series in the house marker style — the shared ``ax.plot`` incantation."""
    ax.plot(
        x,
        y,
        marker="o",
        label=label,
        color=color,
        linewidth=linewidth,
        markersize=LINE_MARKER_SIZE,
        markeredgecolor=FIGURE_BACKGROUND_COLOR,
        markeredgewidth=LINE_MARKER_EDGE_WIDTH,
        solid_capstyle="round",
        zorder=3,
    )


def plot_line(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str,
    output_path: Path,
    rotate_x: int | None = None,
) -> None:
    """Plot a single-series line chart."""
    df = prepare_dataframe(df, x_col, y_col)
    data = df.sort_values(x_col).copy()

    # Ensure numeric x-axis values
    data[x_col] = pd.to_numeric(data[x_col], errors="coerce")
    data = data.dropna(subset=[x_col])

    if data.empty:
        raise ValueError("No valid numeric x-axis values")

    with figure_context() as (fig, ax):
        _draw_series_line(ax, data[x_col], data[y_col], PRIMARY_PALETTE[2])
        ax.fill_between(
            data[x_col],
            data[y_col],
            0,
            color=PRIMARY_PALETTE[2],
            alpha=LINE_FILL_ALPHA,
            zorder=2,
        )
        annotate_endpoint_badge(
            ax,
            x=float(data[x_col].iloc[-1]),
            y=float(data[y_col].iloc[-1]),
            text=f"{y_col} {format_chart_value(float(data[y_col].iloc[-1]))}",
            color=PRIMARY_PALETTE[2],
            y_offset=-4,
        )

        _style_numeric_line_axes(ax, float(data[x_col].min()), float(data[x_col].max()))

        finalize_chart(
            fig=fig,
            ax=ax,
            title=title,
            xlabel=x_col,
            ylabel=y_col,
            output_path=output_path,
            rotate_x=rotate_x,
            grid_axis="y",
            record_count=len(data),
        )


def plot_date_line(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str,
    output_path: Path,
    *,
    month_interval: int = 2,
    date_format: str = "%b %Y",
    annotate_peak_and_latest: bool = True,
    rotate_x: int = 30,
) -> None:
    """Plot a time-series line chart with a datetime x-axis.

    Unlike ``plot_line`` (numeric x-axis only), this helper preserves the
    chronological scale via matplotlib's date locators and adds optional
    callout badges on the peak and latest points so growth stories read
    at a glance.
    """
    df = prepare_dataframe(df, x_col, y_col)
    data = df.sort_values(x_col).copy()
    data[x_col] = pd.to_datetime(data[x_col], format="ISO8601", errors="coerce")
    data = data.dropna(subset=[x_col])

    if data.empty:
        raise ValueError("No valid datetime x-axis values")

    with figure_context() as (fig, ax):
        color = PRIMARY_PALETTE[2]

        _draw_series_line(ax, data[x_col], data[y_col], color)
        ax.fill_between(data[x_col], data[y_col], 0, color=color, alpha=LINE_FILL_ALPHA, zorder=2)

        if annotate_peak_and_latest:
            peak_idx = data[y_col].idxmax()
            latest_idx = data.index[-1]
            # Use a set so peak == latest only renders one badge.
            for idx in {peak_idx, latest_idx}:
                row = data.loc[idx]
                label_text = f"{row[x_col]:{date_format}}: {int(row[y_col])}"
                ax.annotate(
                    label_text,
                    xy=(row[x_col], row[y_col]),
                    xytext=(0, DATE_LINE_LABEL_OFFSET_Y),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=ANNOTATION_FONT_SIZE,
                    color=TITLE_COLOR,
                    fontweight=FONT_WEIGHT_SEMIBOLD,
                    bbox={
                        "boxstyle": ENDPOINT_LABEL_BOX_STYLE,
                        "facecolor": FIGURE_BACKGROUND_COLOR,
                        "edgecolor": LEGEND_EDGE_COLOR,
                        "linewidth": CARD_EDGE_LINE_WIDTH,
                    },
                    zorder=4,
                )

        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=month_interval))
        ax.xaxis.set_major_formatter(mdates.DateFormatter(date_format))
        ax.margins(x=DATE_LINE_X_MARGIN, y=DATE_LINE_Y_MARGIN)
        # Guard against singular ylim (and matplotlib's warning) on all-zero series.
        max_y = float(data[y_col].max())
        ax.set_ylim(0, max_y * DATE_LINE_Y_HEADROOM if max_y > 0 else 1.0)

        finalize_chart(
            fig=fig,
            ax=ax,
            title=title,
            xlabel=x_col,
            ylabel=y_col,
            output_path=output_path,
            rotate_x=rotate_x,
            grid_axis="y",
            record_count=len(data),
        )


def plot_stacked_area(
    df: pd.DataFrame,
    x_col: str,
    stack_cols: list[str],
    labels: list[str],
    title: str,
    output_path: Path,
    colors: dict[str, str] | None = None,
    rotate_x: int | None = None,
    xlabel: str | None = None,
    ylabel: str = "count",
) -> None:
    """Plot a stacked area chart for time-oriented series."""
    data = prepare_dataframe(df, x_col, *stack_cols).copy()

    if len(stack_cols) != len(labels):
        raise ValueError("stack_cols and labels must have the same length")

    if not pd.api.types.is_numeric_dtype(data[x_col]):
        parsed_x = pd.to_datetime(data[x_col], format="ISO8601", errors="coerce", utc=True)
        if parsed_x.notna().all():
            data[x_col] = parsed_x.dt.tz_convert(None)
        elif not is_numeric_or_datetime(data[x_col]):
            raise ValueError("Stacked area chart requires numeric or datetime x-axis values")

    data = data.sort_values(x_col)

    with figure_context() as (fig, ax):
        palette = build_palette(len(stack_cols))
        series_colors = [
            colors.get(label, palette[index]) if colors else palette[index] for index, label in enumerate(labels)
        ]
        legend_handles = [
            Patch(facecolor=color, edgecolor="none", label=label)
            for color, label in zip(series_colors, labels, strict=True)
        ]

        collections = ax.stackplot(
            data[x_col],
            *[data[col].astype(float) for col in stack_cols],
            colors=series_colors,
            alpha=STACKED_AREA_ALPHA,
            linewidth=0.9,
            labels=labels,
            zorder=3,
        )

        for collection in collections:
            collection.set_edgecolor(PLOT_BACKGROUND_COLOR)

        if pd.api.types.is_datetime64_any_dtype(data[x_col]):
            locator = mdates.AutoDateLocator(minticks=4, maxticks=8)
            ax.xaxis.set_major_locator(locator)
            ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
        else:
            ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))

        ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
        ax.margins(x=0.02, y=0.08)

        finalize_chart(
            fig=fig,
            ax=ax,
            title=title,
            xlabel=xlabel or x_col,
            ylabel=ylabel,
            output_path=output_path,
            legend=True,
            rotate_x=rotate_x,
            grid_axis="y",
            legend_handles=legend_handles,
            legend_labels=labels,
            legend_loc="lower center",
            legend_bbox_to_anchor=(0.5, -0.30),
            legend_ncol=min(len(labels), 4),
            legend_kwargs={"borderaxespad": 0.0},
            layout_rect=(0, 0.28, 1.0, 1.0),
            record_count=len(data),
        )
