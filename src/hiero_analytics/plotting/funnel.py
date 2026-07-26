"""Funnel chart renderer: stacked centred bands narrowing stage by stage."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from hiero_analytics.config.charts import (
    ANNOTATION_FONT_SIZE,
    DEFAULT_FIGSIZE,
    FONT_WEIGHT_SEMIBOLD,
    PRIMARY_PALETTE,
    TITLE_COLOR,
)

from .base import figure_context, finalize_chart, prepare_dataframe
from .primitives import format_chart_value

FUNNEL_BAND_HEIGHT = 0.72
# Labels sit inside each band, so they flip to white once the fill is dark
# enough to swallow dark text; the ramp is ordered light to dark.
FUNNEL_DARK_TEXT_BANDS = 2


def plot_funnel(
    df: pd.DataFrame,
    stage_col: str,
    share_col: str,
    title: str,
    output_path: Path,
    shades: Sequence[str] | None = None,
) -> None:
    """Plot a centred funnel: one band per stage, width = its share of the top.

    Each band is centred on the axis so successive stages read as a narrowing
    silhouette, and the only value drawn is the share (as a percentage) inside
    the band — counts belong in the companion table or CSV. ``share_col`` holds
    percentages (0-100) already scaled by the caller, so the funnel makes no
    assumption about what the stages count.
    """
    df = prepare_dataframe(df, stage_col, share_col)
    palette = list(shades or PRIMARY_PALETTE)

    with figure_context(figsize=(DEFAULT_FIGSIZE[0], 0.9 * len(df) + 1)) as (fig, ax):
        for position, (_, row) in enumerate(df.iterrows()):
            share = float(row[share_col])
            ax.barh(
                position,
                width=share,
                left=(100 - share) / 2,
                height=FUNNEL_BAND_HEIGHT,
                color=palette[min(position, len(palette) - 1)],
                linewidth=0,
            )
            ax.text(
                50,
                position,
                f"{format_chart_value(share)}%",
                ha="center",
                va="center",
                fontsize=ANNOTATION_FONT_SIZE + 2,
                fontweight=FONT_WEIGHT_SEMIBOLD,
                color=TITLE_COLOR if position < FUNNEL_DARK_TEXT_BANDS else "white",
            )
        ax.set_yticks(range(len(df)), [str(stage) for stage in df[stage_col]])
        ax.invert_yaxis()
        ax.set_xlim(0, 100)
        # No x ticks: the band widths and their in-band labels carry the value,
        # and an empty tick list means grid_axis="x" draws no gridlines. That
        # axis choice matters — grid_axis=None takes style_axes' non-cartesian
        # branch, which hides *all* tick labels including the stage names.
        ax.set_xticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)

        finalize_chart(
            fig=fig,
            ax=ax,
            title=title,
            xlabel="",
            ylabel="",
            output_path=output_path,
            grid_axis="x",
            record_count=len(df),
        )
