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
  ``channel,last_message,d30,d90,d365,total``. Category is derived from the
  channel name by ``_categorize_channel``; any ``category`` column in the
  CSV is ignored.
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

import pandas as pd

from hiero_analytics.config.charts import MUTED_HISTORICAL_COLOR, PRIMARY_PALETTE
from hiero_analytics.config.paths import INPUTS_DIR, ensure_org_dirs
from hiero_analytics.plotting.bars import plot_bar, plot_stacked_bar
from hiero_analytics.plotting.lines import plot_date_line

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


def _categorize_channel(channel: str) -> str:
    """Map a Discord channel name to its Hiero topic area.

    Identity channels often contain ``-sdk-`` too (e.g. ``hiero-did-sdk-js``),
    so identity rules win first. SDK / governance / core / tooling keywords
    are checked next, with anything unmatched bucketed as Community.
    """
    name = channel.lower()
    if "-did-" in name or "-identity-" in name or name.startswith("heka"):
        return "Identity"
    if (
        "-sdk-" in name
        or name.endswith("-sdk")
        or "enterprise-java" in name
        or "playground" in name
    ):
        return "SDKs"
    if (
        name.endswith("-maintainers")
        or name.endswith("-hips")
        or name.endswith("-community-management")
    ):
        return "Governance"
    if name.endswith("-consensus-node") or name.endswith("-mirror-node"):
        return "Core"
    if name == "solo" or name.endswith("-solo-action"):
        return "Tooling"
    return "Community"


def load_channels_df() -> pd.DataFrame:
    """Load the per-channel snapshot from local CSV (never committed).

    Any ``category`` column in the CSV is replaced by the deterministic
    result of ``_categorize_channel`` so fresh exports don't need manual
    re-categorisation.
    """
    path = _resolve_path("HIERO_DISCORD_CHANNELS_CSV", DEFAULT_CHANNELS_CSV)
    if not path.exists():
        raise FileNotFoundError(
            f"Channels CSV not found at {path}. "
            "Place the snapshot there or set HIERO_DISCORD_CHANNELS_CSV."
        )
    df = pd.read_csv(path)
    df["channel_label"] = "#" + df["channel"]
    df["category"] = df["channel"].apply(_categorize_channel)
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
    start = series["month"].min().strftime("%b %Y")
    end = series["month"].max().strftime("%b %Y")
    plot_date_line(
        series,
        x_col="month",
        y_col="messages",
        title=f"Hiero Discord — Monthly message volume ({start} → {end})",
        output_path=output_path,
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
