"""Pie and donut chart helpers for analytics summaries."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from hiero_analytics.config.charts import (
    ANNOTATION_FONT_SIZE,
    CENTER_TOTAL_FONT_SIZE,
    DONUT_EDGE_LINE_WIDTH,
    DONUT_PERCENTAGE_DISTANCE,
    DONUT_RADIUS,
    DONUT_START_ANGLE,
    DONUT_WIDTH,
    FONT_WEIGHT_SEMIBOLD,
    MUTED_TEXT_COLOR,
    PLOT_BACKGROUND_COLOR,
    TITLE_COLOR,
)

from .base import create_figure, finalize_chart, prepare_dataframe, style_legend
from .primitives import format_chart_value


def _format_donut_pct(pct: float) -> str:
    """Show only meaningful percentage labels to reduce clutter."""
    return f"{pct:.0f}%" if pct >= 5 else ""


def plot_pie(
    df: pd.DataFrame,
    label_col: str,
    value_col: str,
    title: str,
    output_path: Path,
    colors: dict[str, str] | None = None,
    label_order: Sequence[str] | None = None,
    legend_title: str | None = None,
    center_label: str | None = None,
    donut: bool = True,
) -> None:
    """
    Plot a pie chart.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing pie chart data.
    label_col : str
        Column containing labels for each slice.
    value_col : str
        Column containing numeric values for each slice.
    title : str
        Chart title.
    output_path : Path
        File path where the chart image will be saved.
    colors : dict[str, str], optional
        Mapping of label -> color.
    label_order : Sequence[str] | None, optional
        Preferred label order for the legend and slices.
    legend_title : str | None, optional
        Title shown above the legend. Defaults to a humanized label column
        name.
    center_label : str | None, optional
        Optional subtitle rendered beneath the total in the donut center.
    """
    data = prepare_dataframe(df, label_col, value_col)

    if data.empty:
        raise ValueError("No valid data available for plotting")

    data[label_col] = data[label_col].astype(str)
    total = float(data[value_col].sum())

    if total <= 0:
        raise ValueError("Pie chart values must sum to a positive total")

    if (data[value_col] < 0).any():
        raise ValueError("Pie chart values must be non-negative")

    if label_order is not None:
        present_labels = list(dict.fromkeys(data[label_col].tolist()))
        ordered_labels = [label for label in label_order if label in present_labels]
        remaining_labels = [label for label in present_labels if label not in ordered_labels]
        categories = [*ordered_labels, *remaining_labels]
        data[label_col] = pd.Categorical(data[label_col], categories=categories, ordered=True)
        data = data.sort_values(label_col)
        data[label_col] = data[label_col].astype(str)
    else:
        data = data.sort_values(value_col, ascending=False)

    slice_colors = None
    if colors:
        slice_colors = [colors.get(str(label)) for label in data[label_col]]

    fig, ax = create_figure()

    percentages = data[value_col] / total * 100
    # Put the detailed breakdown into the legend so the donut stays visually
    # clean while still showing counts and percentages.
    legend_labels = [
        f"{label}  {format_chart_value(float(value))} ({pct:.0f}%)"
        for label, value, pct in zip(data[label_col], data[value_col], percentages, strict=True)
    ]

    wedge_kwargs = {"edgecolor": PLOT_BACKGROUND_COLOR, "linewidth": DONUT_EDGE_LINE_WIDTH}
    if donut:
        wedge_kwargs["width"] = DONUT_WIDTH  # leave a hole; omit for a filled pie
    wedges, _, _ = ax.pie(
        data[value_col],
        autopct=_format_donut_pct,
        pctdistance=DONUT_PERCENTAGE_DISTANCE if donut else 0.62,
        startangle=DONUT_START_ANGLE,
        colors=slice_colors,
        radius=DONUT_RADIUS,
        wedgeprops=wedge_kwargs,
        textprops={
            "color": TITLE_COLOR,
            "fontsize": ANNOTATION_FONT_SIZE,
            "fontweight": FONT_WEIGHT_SEMIBOLD,
        },
    )

    legend = ax.legend(
        wedges,
        legend_labels,
        title=legend_title or label_col.replace("_", " ").title(),
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
    )
    style_legend(legend)

    # The centre total/label only makes sense in the donut's hole; a filled pie omits it.
    if donut:
        ax.text(
            0,
            0.08 if center_label else 0,
            format_chart_value(total),
            ha="center",
            va="center",
            fontsize=CENTER_TOTAL_FONT_SIZE,
            fontweight=FONT_WEIGHT_SEMIBOLD,
            color=TITLE_COLOR,
        )
        if center_label:
            ax.text(
                0,
                -0.11,
                center_label,
                ha="center",
                va="center",
                fontsize=ANNOTATION_FONT_SIZE,
                color=MUTED_TEXT_COLOR,
            )

    ax.set_aspect("equal")

    finalize_chart(
        fig=fig,
        ax=ax,
        title=title,
        xlabel="",
        ylabel="",
        output_path=output_path,
        grid_axis=None,
        layout_rect=(0, 0, 0.82, 1),
    )
