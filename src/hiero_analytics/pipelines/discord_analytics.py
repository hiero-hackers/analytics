"""
Hiero Discord analytics runner.

Generates tables that summarise activity in the Hiero category of the
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

Tables are written to ``outputs/data/org/hiero-ledger/``.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from hiero_analytics.config.paths import INPUTS_DIR, ensure_org_dirs
from hiero_analytics.export.save import save_dataframe, write_output_meta

ORG = "hiero-ledger"

# Snapshot date for the underlying export; "last 30 days" windows are
# anchored here so the exported tables stay accurate when re-run later.
SNAPSHOT_DATE = date(2026, 5, 12)

DEFAULT_CHANNELS_CSV = INPUTS_DIR / "hiero_discord_channels.csv"
DEFAULT_MONTHLY_CSV = INPUTS_DIR / "hiero_discord_monthly_traffic.csv"


logger = logging.getLogger(__name__)


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
    if "-sdk-" in name or name.endswith("-sdk") or "enterprise-java" in name or "playground" in name:
        return "SDKs"
    if name.endswith("-maintainers") or name.endswith("-hips") or name.endswith("-community-management"):
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
            f"Channels CSV not found at {path}. Place the snapshot there or set HIERO_DISCORD_CHANNELS_CSV."
        )
    df = pd.read_csv(path)
    for row in df.itertuples():
        if not (row.d30 <= row.d90 <= row.d365 <= row.total):
            raise ValueError(
                f"Channel {row.channel!r} violates d30<=d90<=d365<=total: "
                f"d30={row.d30}, d90={row.d90}, d365={row.d365}, total={row.total}"
            )
    df["channel_label"] = "#" + df["channel"]
    df["category"] = df["channel"].apply(_categorize_channel)
    return df


def load_monthly_df() -> pd.DataFrame:
    """Load monthly message volume from local CSV (never committed)."""
    path = _resolve_path("HIERO_DISCORD_MONTHLY_CSV", DEFAULT_MONTHLY_CSV)
    if not path.exists():
        raise FileNotFoundError(
            f"Monthly traffic CSV not found at {path}. Place the export there or set HIERO_DISCORD_MONTHLY_CSV."
        )
    df = pd.read_csv(path)
    df["month"] = pd.to_datetime(df["month"] + "-01")
    return df.sort_values("month").reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Table builders
# --------------------------------------------------------------------------- #


def category_breakdown(channels: pd.DataFrame) -> pd.DataFrame:
    """Messages per topical category: all-time, last 90 days, and the earlier remainder, busiest first."""
    grouped = (
        channels.groupby("category", as_index=False)
        .agg(total=("total", "sum"), last_90d=("d90", "sum"))
        .sort_values("total", ascending=False, kind="stable")
        .reset_index(drop=True)
    )
    grouped["earlier"] = grouped["total"] - grouped["last_90d"]
    return grouped


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main() -> None:
    """Generate the Hiero Discord tables."""
    data_dir = ensure_org_dirs(ORG)

    channels = load_channels_df()
    monthly = load_monthly_df()

    categories = category_breakdown(channels)
    save_dataframe(categories, data_dir / "hiero_discord_channel_categories.csv")
    save_dataframe(channels[["channel_label", "d30"]], data_dir / "hiero_discord_recent_activity_30d.csv")
    save_dataframe(monthly, data_dir / "hiero_discord_monthly_traffic.csv")

    for name in ("channel_categories", "recent_activity_30d", "monthly_traffic"):
        write_output_meta(
            data_dir / f"hiero_discord_{name}.csv",
            generated_at=datetime.combine(SNAPSHOT_DATE, datetime.min.time(), tzinfo=UTC),
        )

    logger.info("Hiero Discord tables written to %s", data_dir)
