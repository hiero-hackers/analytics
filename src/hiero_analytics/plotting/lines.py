"""Line chart primitives styled to match the shared analytics theme."""

from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.ticker as ticker
import pandas as pd
from matplotlib.patches import Patch

from hiero_analytics.config.charts import (
    ANNOTATION_FONT_SIZE,
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

from .base import create_figure, finalize_chart, prepare_dataframe
from .primitives import annotate_endpoint_badge, build_palette, format_chart_value, is_numeric_or_datetime

# Headroom multiplier on the y-axis so badge annotations have room above the
# peak marker without overlapping the chart frame.
DATE_LINE_Y_HEADROOM = 1.25
DATE_LINE_X_MARGIN = 0.02
DATE_LINE_Y_MARGIN = 0.18
DATE_LINE_LABEL_OFFSET_Y = 14
DATE_LINE_BBOX_LINEWIDTH = 0.9


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

    fig, ax = create_figure()

    ax.plot(
        data[x_col],
        data[y_col],
        marker="o",
        color=PRIMARY_PALETTE[2],
        linewidth=LINE_WIDTH,
        markersize=LINE_MARKER_SIZE,
        markeredgecolor=FIGURE_BACKGROUND_COLOR,
        markeredgewidth=LINE_MARKER_EDGE_WIDTH,
        solid_capstyle="round",
        zorder=3,
    )
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

    ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax.set_xlim(float(data[x_col].min()) - 0.15, float(data[x_col].max()) + 0.45)
    ax.margins(x=0.03, y=0.16)

    finalize_chart(
        fig=fig,
        ax=ax,
        title=title,
        xlabel=x_col,
        ylabel=y_col,
        output_path=output_path,
        rotate_x=rotate_x,
        grid_axis="y",
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
    data[x_col] = pd.to_datetime(data[x_col], errors="coerce")
    data = data.dropna(subset=[x_col])

    if data.empty:
        raise ValueError("No valid datetime x-axis values")

    fig, ax = create_figure()
    color = PRIMARY_PALETTE[2]

    ax.plot(
        data[x_col],
        data[y_col],
        marker="o",
        color=color,
        linewidth=LINE_WIDTH,
        markersize=LINE_MARKER_SIZE,
        markeredgecolor=FIGURE_BACKGROUND_COLOR,
        markeredgewidth=LINE_MARKER_EDGE_WIDTH,
        solid_capstyle="round",
        zorder=3,
    )
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
                    "linewidth": DATE_LINE_BBOX_LINEWIDTH,
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
    )


def plot_multiline(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    group_col: str,
    title: str,
    output_path: Path,
    colors: dict[str, str] | None = None,
    rotate_x: int | None = None,
) -> None:
    """
    Plot a multi-series line chart grouped by a column.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataset.

    x_col : str
        Column used for x-axis.

    y_col : str
        Column used for y values.

    group_col : str
        Column defining the separate series.

    title : str
        Chart title.

    output_path : Path
        File path where the chart image will be saved.

    colors : dict[str, str] | None
        Optional mapping of series label -> color.

    rotate_x : int | None
        Optional x-axis label rotation.
    """
    df = prepare_dataframe(df, x_col, y_col, group_col).copy()

    pivot = df.pivot_table(index=x_col, columns=group_col, values=y_col, aggfunc="sum").sort_index()

    if pivot.empty:
        raise ValueError("Pivot produced an empty dataset")

    pivot.index = pd.to_numeric(pivot.index, errors="coerce")
    pivot = pivot.dropna(axis=0, how="all")
    pivot = pivot[~pivot.index.isna()]

    if pivot.empty:
        raise ValueError("No valid numeric x-axis values")

    fig, ax = create_figure()
    palette = build_palette(len(pivot.columns))
    endpoint_offsets = [-14, 0, 14, 28, 42]

    for index, column in enumerate(pivot.columns):
        color = colors.get(column) if colors else palette[index]
        is_total = str(column).lower() == "total"
        series = pivot[column].dropna()

        ax.plot(
            series.index,
            series,
            marker="o",
            label=str(column),
            color=color,
            linewidth=3 if is_total else 2.4,
            markersize=LINE_MARKER_SIZE,
            markeredgecolor=FIGURE_BACKGROUND_COLOR,
            markeredgewidth=LINE_MARKER_EDGE_WIDTH,
            solid_capstyle="round",
            zorder=3,
        )
        if is_total:
            # The total line gets a subtle area fill so it reads as the main
            # trend without overpowering the other series.
            ax.fill_between(
                series.index,
                series,
                0,
                color=color,
                alpha=LINE_FILL_ALPHA,
                zorder=2,
            )
        annotate_endpoint_badge(
            ax,
            x=float(series.index[-1]),
            y=float(series.iloc[-1]),
            text=f"{column} {format_chart_value(float(series.iloc[-1]))}",
            color=color,
            y_offset=endpoint_offsets[index % len(endpoint_offsets)],
        )

    ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax.set_xlim(float(pivot.index.min()) - 0.15, float(pivot.index.max()) + 0.45)
    ax.margins(x=0.03, y=0.16)

    legend_count = len(pivot.columns)

    ## Prefer Bottom legend, Right legend only when many items
    if legend_count > 6:
        legend_loc = "upper left"
        legend_bbox_to_anchor = (1.02, 1.0)
        legend_ncol = 1
        layout_rect = (0, 0, 0.85, 1.0)
    else:
        legend_loc = "lower center"
        legend_bbox_to_anchor = (0.5, -0.18)
        legend_ncol = min(legend_count, 4)
        layout_rect = (0, 0.12, 1.0, 1.0)

    finalize_chart(
        fig=fig,
        ax=ax,
        title=title,
        xlabel=x_col,
        ylabel=y_col,
        output_path=output_path,
        legend=True,
        rotate_x=rotate_x,
        grid_axis="y",
        legend_loc=legend_loc,
        legend_bbox_to_anchor=legend_bbox_to_anchor,
        legend_ncol=legend_ncol,
        legend_kwargs={"borderaxespad": 0.0},
        layout_rect=layout_rect,
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
        parsed_x = pd.to_datetime(data[x_col], errors="coerce", utc=True)
        if parsed_x.notna().all():
            data[x_col] = parsed_x.dt.tz_convert(None)
        elif not is_numeric_or_datetime(data[x_col]):
            raise ValueError("Stacked area chart requires numeric or datetime x-axis values")

    data = data.sort_values(x_col)

    fig, ax = create_figure()
    palette = build_palette(len(stack_cols))
    series_colors = [colors.get(label, palette[index]) if colors else palette[index] for index, label in enumerate(labels)]
    legend_handles = [Patch(facecolor=color, edgecolor="none", label=label) for color, label in zip(series_colors, labels, strict=True)]

    collections = ax.stackplot(
        data[x_col],
        *[data[col].astype(float) for col in stack_cols],
        colors=series_colors,
        alpha=0.96,
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
        legend_bbox_to_anchor=(0.5, -0.14),
        legend_ncol=min(len(labels), 4),
        legend_kwargs={"borderaxespad": 0.0},
        layout_rect=(0, 0.14, 1.0, 1.0),
    )
