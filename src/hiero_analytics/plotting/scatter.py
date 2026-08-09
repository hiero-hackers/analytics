"""Scatter plot with linear regression for the analytics design system."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from hiero_analytics.config.charts import (
    ANNOTATION_FONT_SIZE,
    MUTED_TEXT_COLOR,
    PRIMARY_PALETTE,
    TITLE_COLOR,
)
from hiero_analytics.plotting.base import (
    figure_context,
    finalize_chart,
    prepare_dataframe,
)
from hiero_analytics.plotting.primitives import styled_text_badge


def plot_release_timeline(
    df: pd.DataFrame,
    *,
    title: str,
    output_path: Path,
) -> None:
    """Per-repo release dot/strip timeline, y-axis sorted by release count.

    Expects one row per release with ``repo``, ``published_at``, and
    ``is_prerelease`` columns (i.e. the shape of
    :func:`hiero_analytics.analysis.releases.build_release_timeline`) —
    callers apply any date-window filtering before calling this.

    Design settled against real hiero-ledger data on #331: a per-repo
    release-count label (not more dots) keeps a high-cadence repo's row
    legible — the dot pattern reads rhythm/gaps/coordinated release trains
    qualitatively, while exact volume is precise text instead of something
    the reader has to count through overlapping markers. The y-axis is
    sorted by count (busiest at top) so cadence tiers are visible from scan
    order alone.

    Unlike ``build_release_staleness``, this chart is scoped to repos with
    at least one release in the given data — a repo with zero releases has
    nothing to plot, and most zero-release repos turned out to be
    structurally non-shipping (docs/governance/meta), so an empty row here
    would mostly be visual noise. The honest-denominator obligation lives in
    the staleness table/CSV next to this chart, not in the chart itself.
    """
    df = prepare_dataframe(df, "repo", "published_at")

    order = df.groupby("repo").size().sort_values(ascending=True).index.tolist()
    y_pos = {repo: i for i, repo in enumerate(order)}

    with figure_context(figsize=(12, max(4, 0.42 * len(order) + 1.5))) as (fig, ax):
        stable = df[~df["is_prerelease"]]
        pre = df[df["is_prerelease"]]

        ax.scatter(
            stable["published_at"],
            stable["repo"].map(y_pos),
            color=PRIMARY_PALETTE[2],
            alpha=0.45,
            s=42,
            edgecolors="none",
            zorder=3,
            label="Release",
        )
        ax.scatter(
            pre["published_at"],
            pre["repo"].map(y_pos),
            color=PRIMARY_PALETTE[0],
            alpha=0.6,
            s=42,
            marker="D",
            edgecolors="none",
            zorder=4,
            label="Prerelease",
        )

        ax.set_yticks(list(y_pos.values()))
        ax.set_yticklabels(list(y_pos.keys()))
        ax.margins(x=0.02, y=0.03)

        counts = df.groupby("repo").size()
        for repo, y in y_pos.items():
            ax.text(
                1.005,
                y,
                str(int(counts.get(repo, 0))),
                transform=ax.get_yaxis_transform(),
                va="center",
                ha="left",
                fontsize=ANNOTATION_FONT_SIZE,
                color=MUTED_TEXT_COLOR,
            )

        finalize_chart(
            fig=fig,
            ax=ax,
            title=title,
            xlabel="Release date",
            ylabel="",
            output_path=output_path,
            legend=True,
            legend_loc="upper left",
            legend_bbox_to_anchor=(1.06, 1.0),
            grid_axis="x",
            record_count=len(df),
        )


def plot_scatter_with_regression(
    df: pd.DataFrame,
    *,
    x_col: str,
    y_col: str,
    title: str,
    xlabel: str,
    ylabel: str,
    output_path: Path,
) -> None:
    """
    Standardized scatter + regression chart.

    Features:
    - Clean scatter styling
    - Sorted regression line
    - Slope + correlation annotation
    - Consistent design system integration
    """
    # -------------------------
    # Prepare data (shared validation: required columns, non-empty, drop NA)
    # -------------------------
    df = prepare_dataframe(df, x_col, y_col)

    x = df[x_col].astype(float)
    y = df[y_col].astype(float)

    # -------------------------
    # Regression (needs at least two points — a single point cannot determine
    # a line, and an unguarded polyfit warns "poorly conditioned")
    # -------------------------
    has_regression = len(df) > 1
    if has_regression:
        slope, intercept = np.polyfit(x, y, 1)
        y_pred = slope * x + intercept
        r = np.corrcoef(x, y)[0, 1]

        # sort for clean line rendering
        order = np.argsort(x)
        x_sorted = x.iloc[order]
        y_pred_sorted = y_pred.iloc[order]

    # -------------------------
    # Plot
    # -------------------------
    with figure_context() as (fig, ax):
        # Scatter
        ax.scatter(
            x,
            y,
            color=PRIMARY_PALETTE[2],
            alpha=0.55,
            s=38,
            edgecolors="none",
            zorder=3,
        )

        if has_regression:
            # Regression line
            ax.plot(
                x_sorted,
                y_pred_sorted,
                color=PRIMARY_PALETTE[0],
                linewidth=2.4,
                zorder=4,
            )

            # -------------------------
            # Annotations (styled)
            # -------------------------
            styled_text_badge(ax, x=0.02, y=0.96, text=f"Slope {slope:.2f}", color=TITLE_COLOR)

            if not np.isnan(r):
                ax.text(
                    0.02,
                    0.88,
                    f"r = {r:.2f}",
                    transform=ax.transAxes,
                    fontsize=ANNOTATION_FONT_SIZE,
                    color=MUTED_TEXT_COLOR,
                    va="top",
                    zorder=5,
                )

        # -------------------------
        # Layout polish
        # -------------------------
        ax.margins(x=0.05, y=0.08)
        ax.set_ylim(bottom=0)

        # -------------------------
        # Finalize
        # -------------------------
        finalize_chart(
            fig=fig,
            ax=ax,
            title=title,
            xlabel=xlabel,
            ylabel=ylabel,
            output_path=output_path,
            legend=False,
            grid_axis="both",
            record_count=len(df),
        )
