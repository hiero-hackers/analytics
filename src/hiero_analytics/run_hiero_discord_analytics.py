"""
Hiero Discord analytics runner.

Generates charts that summarise activity in the Hiero category of the
Linux Foundation Decentralized Trust (LFDT) Discord. The numbers are
sourced from a manually-exported category report and the goal is to surface:

- Growth trajectory of the community
- Where conversation is most active right now
- Topical breadth across SDKs, identity, and community channels

The raw counts are not committed. Two CSVs are read from
``inputs/`` by default (the directory is gitignored):

- ``hiero_discord_channels.csv`` — per-channel snapshot with columns
  ``channel,last_message,d30,d90,d365,total,category``
- ``hiero_discord_monthly_traffic.csv`` — monthly volume with columns
  ``month,messages``

Override either path with ``HIERO_DISCORD_CHANNELS_CSV`` /
``HIERO_DISCORD_MONTHLY_CSV``.

Charts are written to ``outputs/charts/org/hiero-ledger/``.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import matplotlib.dates as mdates
import pandas as pd

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
    MUTED_HISTORICAL_COLOR,
    PRIMARY_PALETTE,
    TITLE_COLOR,
)
from hiero_analytics.config.paths import INPUTS_DIR, ensure_org_dirs
from hiero_analytics.plotting.bars import plot_bar, plot_stacked_bar
from hiero_analytics.plotting.base import create_figure, finalize_chart

ORG = "hiero-ledger"

# Snapshot date for the underlying export; "last 30 days" windows are
# anchored here so the chart titles stay accurate when re-run later.
SNAPSHOT_DATE = date(2026, 5, 12)

DEFAULT_CHANNELS_CSV = INPUTS_DIR / "hiero_discord_channels.csv"
DEFAULT_MONTHLY_CSV = INPUTS_DIR / "hiero_discord_monthly_traffic.csv"


def _resolve_path(env_var: str, default: Path) -> Path:
    """Allow ops to point the runner at an out-of-tree CSV without editing code."""
    override = os.environ.get(env_var)
    return Path(override).expanduser() if override else default


def load_channels_df() -> pd.DataFrame:
    """Load the per-channel snapshot from local CSV (never committed)."""
    path = _resolve_path("HIERO_DISCORD_CHANNELS_CSV", DEFAULT_CHANNELS_CSV)
    if not path.exists():
        raise FileNotFoundError(
            f"Channels CSV not found at {path}. "
            "Place the snapshot there or set HIERO_DISCORD_CHANNELS_CSV."
        )
    df = pd.read_csv(path)
    df["channel_label"] = "#" + df["channel"]
    return df


def load_monthly_df() -> pd.DataFrame:
    """Load monthly message volume from local CSV (never committed)."""
    path = _resolve_path("HIERO_DISCORD_MONTHLY_CSV", DEFAULT_MONTHLY_CSV)
    if not path.exists():
        raise FileNotFoundError(
            f"Monthly traffic CSV not found at {path}. "
            "Place the export there or set HIERO_DISCORD_MONTHLY_CSV."
        )
    df = pd.read_csv(path)
    df["month"] = pd.to_datetime(df["month"] + "-01")
    return df.sort_values("month").reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Chart builders
# --------------------------------------------------------------------------- #


def plot_recent_activity_30d(channels: pd.DataFrame, output_path: Path, top_n: int = 5) -> None:
    """Top channels by messages in the last 30 days (relative to snapshot)."""
    df = (
        channels
        .loc[lambda d: d["d30"] > 0, ["channel_label", "d30"]]
        .sort_values("d30", ascending=False)
        .head(top_n)
        .rename(columns={"d30": "messages (last 30d)"})
    )
    plot_bar(
        df,
        x_col="channel_label",
        y_col="messages (last 30d)",
        title=f"Hiero Discord — Top {top_n} active channels in last 30 days (to {SNAPSHOT_DATE.isoformat()})",
        output_path=output_path,
    )


def plot_category_breakdown(channels: pd.DataFrame, output_path: Path) -> None:
    """Channel grouping by topical category — total vs last-90-day activity."""
    grouped = (
        channels.groupby("category", as_index=False)
        .agg(total=("total", "sum"), last_90d=("d90", "sum"))
        .sort_values("total", ascending=False)
    )
    plot_stacked_bar(
        df=grouped.rename(
            columns={"total": "earlier", "last_90d": "last 90 days"}
        ).assign(earlier=lambda d: d["earlier"] - d["last 90 days"]),
        x_col="category",
        stack_cols=["last 90 days", "earlier"],
        labels=["Last 90 days", "Earlier history"],
        title="Hiero Discord — Conversation mix by topic area",
        output_path=output_path,
        colors={"Last 90 days": PRIMARY_PALETTE[0], "Earlier history": MUTED_HISTORICAL_COLOR},
        sort_categorical=False,
    )


def plot_monthly_traffic(series: pd.DataFrame, output_path: Path) -> None:
    """Monthly message volume as a date-aware line chart with fill."""
    fig, ax = create_figure()
    color = PRIMARY_PALETTE[2]

    ax.plot(
        series["month"],
        series["messages"],
        marker="o",
        color=color,
        linewidth=LINE_WIDTH,
        markersize=LINE_MARKER_SIZE,
        markeredgecolor=FIGURE_BACKGROUND_COLOR,
        markeredgewidth=LINE_MARKER_EDGE_WIDTH,
        solid_capstyle="round",
        zorder=3,
    )
    ax.fill_between(series["month"], series["messages"], 0, color=color, alpha=LINE_FILL_ALPHA, zorder=2)

    # Annotate peak month and the most recent month so the growth story reads
    # at a glance without crowding every marker.
    peak_idx = int(series["messages"].idxmax())
    latest_idx = len(series) - 1
    for idx in {peak_idx, latest_idx}:
        row = series.iloc[idx]
        label_text = f"{row['month']:%b %Y}: {int(row['messages'])}"
        ax.annotate(
            label_text,
            xy=(row["month"], row["messages"]),
            xytext=(0, 14),
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
                "linewidth": 0.9,
            },
            zorder=4,
        )

    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.margins(x=0.02, y=0.18)
    ax.set_ylim(0, float(series["messages"].max()) * 1.25)

    finalize_chart(
        fig=fig,
        ax=ax,
        title="Hiero Discord — Monthly message volume (Sept 2024 → May 2026)",
        xlabel="month",
        ylabel="messages",
        output_path=output_path,
        rotate_x=30,
        grid_axis="y",
    )


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main() -> None:
    """Generate the Hiero Discord chart bundle."""
    _, charts_dir = ensure_org_dirs(ORG)

    channels = load_channels_df()
    monthly = load_monthly_df()

    plot_monthly_traffic(monthly, charts_dir / "hiero_discord_monthly_traffic.png")
    plot_recent_activity_30d(channels, charts_dir / "hiero_discord_recent_activity_30d.png")
    plot_category_breakdown(channels, charts_dir / "hiero_discord_channel_categories.png")

    print(f"Hiero Discord charts written to {charts_dir}")


if __name__ == "__main__":
    main()
