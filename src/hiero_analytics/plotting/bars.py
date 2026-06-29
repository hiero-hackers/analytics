"""Bar chart primitives with a shared analytics house style."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pandas as pd
from matplotlib.axes import Axes
from matplotlib.patches import FancyBboxPatch, Patch, Rectangle

from hiero_analytics.config.charts import ANNOTATION_FONT_SIZE, DEFAULT_FIGSIZE, FONT_WEIGHT_SEMIBOLD, PRIMARY_PALETTE, TITLE_COLOR

from .base import (
    adaptive_legend_placement,
    create_figure,
    finalize_chart,
    prepare_dataframe,
)
from .primitives import build_palette, format_chart_value, is_numeric_or_datetime

BAR_HEIGHT = 0.68
BAR_WIDTH = 0.62
BAR_ROUNDING_RATIO = 0.18
HORIZONTAL_ROW_HEIGHT = 0.42  # inches per bar for auto-sizing horizontal charts
HORIZONTAL_FIGURE_OVERHEAD = 3.5   # inches reserved for title, axes, legend
HORIZONTAL_FIGURE_MIN_HEIGHT = 6.0
HORIZONTAL_FIGURE_WIDTH = 14.0
ANNOTATION_PADDING_RATIO = 0.015
ANNOTATION_MIN_PADDING = 0.75
HORIZONTAL_AXIS_LIMIT_RATIO = 1.12
HORIZONTAL_AXIS_MIN_EXTRA = 0.5
HORIZONTAL_X_MARGIN = 0.08
HORIZONTAL_Y_MARGIN = 0.04
VERTICAL_X_MARGIN = 0.04
VERTICAL_Y_MARGIN = 0.08
STACKED_BAR_ALPHA = 0.98
BAR_ZORDER = 3
ANNOTATION_ZORDER = 4


def _should_use_horizontal(df: pd.DataFrame, x_col: str, rotate_x: int | None) -> bool:
    """Use horizontal bars for crowded categorical charts."""
    if is_numeric_or_datetime(df[x_col]):
        return False

    # Repo names and other long categorical labels are much easier to scan in a
    # horizontal layout, especially once the chart has many rows.
    labels = df[x_col].astype(str)
    return len(df) >= 8 or rotate_x is not None or int(labels.str.len().max()) > 12


def _compute_annotation_padding(max_value: float) -> float:
    """Return label padding with a small fixed floor for low-count charts."""
    return max(max_value * ANNOTATION_PADDING_RATIO, ANNOTATION_MIN_PADDING)


def _compute_horizontal_axis_limit(max_value: float, annotation_padding: float) -> float:
    """Leave enough room for labels while keeping the horizontal axis compact."""
    if max_value <= 0:
        return 1.0

    return max(
        max_value * HORIZONTAL_AXIS_LIMIT_RATIO,
        max_value + annotation_padding + HORIZONTAL_AXIS_MIN_EXTRA,
    )


def _annotate_bar_totals(
    ax: Axes,
    patches: list[Rectangle],
    values: pd.Series,
    *,
    horizontal: bool,
) -> None:
    """Add clean total labels to the ends of bars."""
    if values.empty:
        return

    max_value = float(values.max())
    padding = _compute_annotation_padding(max_value)

    for patch, value in zip(patches, values, strict=True):
        if value <= 0:
            continue

        if horizontal:
            ax.text(
                float(value) + padding,
                patch.get_y() + patch.get_height() / 2,
                format_chart_value(float(value)),
                va="center",
                ha="left",
                fontsize=ANNOTATION_FONT_SIZE,
                color=TITLE_COLOR,
                fontweight=FONT_WEIGHT_SEMIBOLD,
                zorder=ANNOTATION_ZORDER,
            )
        else:
            ax.text(
                patch.get_x() + patch.get_width() / 2,
                float(value) + padding,
                format_chart_value(float(value)),
                va="bottom",
                ha="center",
                fontsize=ANNOTATION_FONT_SIZE,
                color=TITLE_COLOR,
                fontweight=FONT_WEIGHT_SEMIBOLD,
                zorder=ANNOTATION_ZORDER,
            )


def _round_bar_patches(
    ax: Axes,
    patches: list[Rectangle],
    *,
    rounding_ratio: float = BAR_ROUNDING_RATIO,
) -> None:
    """Replace default bar rectangles with softly rounded patches."""
    for patch in patches:
        width = patch.get_width()
        height = patch.get_height()

        if width == 0 or height == 0:
            continue

        rounding = min(abs(width), abs(height)) * rounding_ratio
        rounded = FancyBboxPatch(
            (patch.get_x(), patch.get_y()),
            width,
            height,
            boxstyle=f"round,pad=0,rounding_size={rounding}",
            facecolor=patch.get_facecolor(),
            edgecolor="none",
            linewidth=0,
            mutation_aspect=1,
            transform=ax.transData,
            zorder=patch.get_zorder(),
        )
        rounded.set_clip_on(True)
        rounded.set_clip_path(ax.patch)
        ax.add_patch(rounded)
        patch.set_visible(False)


def plot_bar(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str,
    output_path: Path,
    rotate_x: int | None = None,
    colors: dict[str, str] | None = None,
) -> None:
    """Plot a standard bar chart."""
    df = prepare_dataframe(df, x_col, y_col).copy()

    # Sort bars by x-axis for numeric/datetime categories, but keep original order for categorical axes (often already sorted by total count) to preserve readability and avoid reordering issues with long labels. Rotate bars to horizontal if there are many categories or if x-axis labels are long.
    if not pd.api.types.is_categorical_dtype(df[x_col]):
        df = df.sort_values(x_col) if is_numeric_or_datetime(df[x_col]) else df.sort_values(y_col, ascending=False)    # Auto-switch to a more report-like horizontal layout for crowded categories.
    horizontal = _should_use_horizontal(df, x_col, rotate_x)

    fig, ax = create_figure()

    bar_colors = (
        [colors.get(str(x), PRIMARY_PALETTE[0]) for x in df[x_col]] if colors else [PRIMARY_PALETTE[2]] * len(df)
    )

    bars = (
        ax.barh(
            df[x_col].astype(str),
            df[y_col],
            color=bar_colors,
            height=BAR_HEIGHT,
            linewidth=0,
            zorder=BAR_ZORDER,
        )
        if horizontal
        else ax.bar(
            df[x_col],
            df[y_col],
            color=bar_colors,
            width=BAR_WIDTH,
            linewidth=0,
            zorder=BAR_ZORDER,
        )
    )
    patches = cast(list[Rectangle], list(bars.patches))
    _round_bar_patches(ax, patches)
    _annotate_bar_totals(ax, patches, df[y_col], horizontal=horizontal)

    if horizontal:
        ax.invert_yaxis()
        # Leave room for end labels on the right.
        max_value = float(df[y_col].max())
        padding = _compute_annotation_padding(max_value)
        ax.margins(y=HORIZONTAL_Y_MARGIN, x=HORIZONTAL_X_MARGIN)
        ax.set_xlim(0, _compute_horizontal_axis_limit(max_value, padding))
    else:
        ax.margins(x=VERTICAL_X_MARGIN, y=VERTICAL_Y_MARGIN)

    finalize_chart(
        fig=fig,
        ax=ax,
        title=title,
        xlabel=y_col if horizontal else x_col,
        ylabel="" if horizontal else y_col,
        output_path=output_path,
        rotate_x=None if horizontal else rotate_x,
        grid_axis="x" if horizontal else "y",
    )


def plot_stacked_bar(
    df: pd.DataFrame,
    x_col: str,
    stack_cols: list[str],
    labels: list[str],
    title: str,
    output_path: Path,
    colors: dict[str, str] | None = None,
    rotate_x: int | None = None,
    annotate_totals: bool = True,
    sort_categorical: bool = True,
    legend_inside_bottom_right: bool = False,
    auto_height_for_horizontal: bool = True,
) -> None:
    """
    Plot stacked bar chart.

    Parameters
    ----------
    df : pd.DataFrame
        Data containing categories and stacked values.

    x_col : str
        Column used for x-axis categories.

    stack_cols : list[str]
        Columns containing numeric values to stack.

    labels : list[str]
        Labels corresponding to each stacked column.

    title : str
        Chart title.

    output_path : Path
        Destination path for the saved chart.

    colors : dict[str, str], optional
        Mapping of label -> color.

    rotate_x : int | None
        Optional x-axis label rotation.

    annotate_totals : bool
        Whether to annotate bar totals. Defaults to True.

    sort_categorical : bool
        Whether to sort categorical bars by total descending.

    legend_inside_bottom_right : bool
        Place legend inside plot area at lower-right.

    auto_height_for_horizontal : bool
        Expand figure height based on row count for horizontal charts.
    """
    df = prepare_dataframe(df, x_col, *stack_cols).copy()

    if len(stack_cols) != len(labels):
        raise ValueError("stack_cols and labels must have the same length")

    # Choose sorting strategy based on x-axis type:
    # - For numeric/datetime-like x_col, preserve natural/chronological order.
    # - For categorical x_col, sort bars by total size for readability.
    if is_numeric_or_datetime(df[x_col]):
        df = df.sort_values(x_col)
    elif sort_categorical:
        # Repo-level comparisons are easier to read when ordered by total volume.
        df["total"] = df[stack_cols].sum(axis=1)
        df = df.sort_values("total", ascending=False)
    horizontal = _should_use_horizontal(df, x_col, rotate_x)

    # Scale the figure to comfortably fit all rows when using a horizontal layout.
    if horizontal and auto_height_for_horizontal:
        fig_height = max(
            HORIZONTAL_FIGURE_MIN_HEIGHT,
            len(df) * HORIZONTAL_ROW_HEIGHT + HORIZONTAL_FIGURE_OVERHEAD,
        )
        figsize: tuple[float, float] = (HORIZONTAL_FIGURE_WIDTH, fig_height)
    else:
        figsize = DEFAULT_FIGSIZE

    fig, ax = create_figure(figsize=figsize)

    offsets = pd.Series(0, index=df.index, dtype=float)
    totals = df[stack_cols].sum(axis=1)
    palette = build_palette(len(stack_cols))
    legend_handles: list[Patch] = []
    patches: list[Rectangle] = []

    for index, (col, label) in enumerate(zip(stack_cols, labels, strict=True)):
        color = colors.get(label) if colors else palette[index]
        legend_handles.append(Patch(facecolor=color, edgecolor="none", label=label))

        bars = (
            ax.barh(
                df[x_col].astype(str),
                df[col],
                left=offsets,
                label=label,
                color=color,
                height=BAR_HEIGHT,
                linewidth=0,
                alpha=STACKED_BAR_ALPHA,
                zorder=BAR_ZORDER,
            )
            if horizontal
            else ax.bar(
                df[x_col],
                df[col],
                bottom=offsets,
                label=label,
                color=color,
                width=BAR_WIDTH,
                linewidth=0,
                alpha=STACKED_BAR_ALPHA,
                zorder=BAR_ZORDER,
            )
        )
        patches = cast(list[Rectangle], list(bars.patches))
        offsets = offsets.add(df[col], fill_value=0)

    if horizontal:
        ax.invert_yaxis()
        # Place the legend in reserved top whitespace and keep totals at the end
        # of each stack rather than inside the bars.
        max_total = float(totals.max()) if not totals.empty else 0.0
        padding = _compute_annotation_padding(max_total)
        if annotate_totals:
            _annotate_bar_totals(ax, patches, totals, horizontal=True)
        ax.margins(y=HORIZONTAL_Y_MARGIN, x=HORIZONTAL_X_MARGIN)
        ax.set_xlim(0, _compute_horizontal_axis_limit(max_total, padding))
    else:
        if annotate_totals and len(df) <= 12:
            _annotate_bar_totals(ax, patches, totals, horizontal=False)
        ax.margins(x=VERTICAL_X_MARGIN, y=VERTICAL_Y_MARGIN)
        # Force integer ticks when all x values are whole numbers (e.g. years).
        if is_numeric_or_datetime(df[x_col]) and (df[x_col] % 1 == 0).all():
            ax.set_xticks(df[x_col])
            ax.set_xticklabels([str(int(v)) for v in df[x_col]])

    ## Adaptive Legend placement
    labels_count = len(labels)
    placement = adaptive_legend_placement(labels_count)

    # Backward-compatible override.
    if legend_inside_bottom_right:
        placement = {
            "legend_loc": "lower right",
            "legend_bbox_to_anchor": (0.985, 0.02),
            "legend_ncol": min(labels_count, 4),
            "layout_rect": (0.0, 0.0, 1.0, 1.0),
        }

    finalize_chart(
        fig=fig,
        ax=ax,
        title=title,
        xlabel="count" if horizontal else x_col,
        ylabel="" if horizontal else "count",
        output_path=output_path,
        legend=True,
        rotate_x=None if horizontal else rotate_x,
        grid_axis="x" if horizontal else "y",
        legend_handles=legend_handles,
        legend_labels=labels,
        legend_kwargs={"borderaxespad": 0.0},
        **placement,
    )
