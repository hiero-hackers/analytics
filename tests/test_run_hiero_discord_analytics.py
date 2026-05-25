"""Regression tests for the Hiero Discord analytics runner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import matplotlib
import pandas as pd
import pytest

matplotlib.use("Agg")

import hiero_analytics.run_hiero_discord_analytics as runner


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

CHANNELS_CSV_TEXT = (
    "channel,last_message,d30,d90,d365,total\n"
    "hiero-sdk-python,2026-05-11,87,125,322,483\n"
    "hiero-general,2026-05-10,95,124,160,200\n"
    "hiero-sdk-cpp,2026-05-10,27,29,55,56\n"
    "hiero-website,2026-04-28,15,56,155,155\n"
    "hiero-sdk-java,2026-02-02,0,0,4,8\n"        # excluded by d30>0 filter
    "hiero-hips,2026-02-09,0,0,4,9\n"            # excluded by d30>0 filter
)

# Intentionally unsorted to verify load_monthly_df sorts ascending.
MONTHLY_CSV_TEXT = (
    "month,messages\n"
    "2026-01,258\n"
    "2025-12,31\n"
    "2026-02,230\n"
    "2024-09,13\n"
)


@pytest.fixture
def channels_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Write a synthetic channels CSV and point the loader at it via env var."""
    path = tmp_path / "channels.csv"
    path.write_text(CHANNELS_CSV_TEXT)
    monkeypatch.setenv("HIERO_DISCORD_CHANNELS_CSV", str(path))
    return path


@pytest.fixture
def monthly_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Write a synthetic monthly CSV and point the loader at it via env var."""
    path = tmp_path / "monthly.csv"
    path.write_text(MONTHLY_CSV_TEXT)
    monkeypatch.setenv("HIERO_DISCORD_MONTHLY_CSV", str(path))
    return path


# --------------------------------------------------------------------------- #
# Loader tests
# --------------------------------------------------------------------------- #

def test_load_channels_df_reads_csv_and_derives_label_and_category(channels_csv: Path) -> None:
    df = runner.load_channels_df()

    # All CSV columns plus the derived label and (auto-derived) category.
    expected = {"channel", "last_message", "d30", "d90", "d365", "total", "category", "channel_label"}
    assert expected.issubset(df.columns)
    assert len(df) == 6
    assert df.loc[df["channel"] == "hiero-sdk-python", "channel_label"].iloc[0] == "#hiero-sdk-python"
    # Category is derived from the channel name, not the CSV.
    assert df.loc[df["channel"] == "hiero-sdk-python", "category"].iloc[0] == "SDKs"
    assert df.loc[df["channel"] == "hiero-general", "category"].iloc[0] == "Community"
    assert df.loc[df["channel"] == "hiero-hips", "category"].iloc[0] == "Governance"


@pytest.mark.parametrize(
    "channel, expected",
    [
        # Identity wins over SDKs when both keywords appear.
        ("hiero-did-sdk-js", "Identity"),
        ("hiero-did-sdk-python", "Identity"),
        ("hiero-identity-collaboration-hub", "Identity"),
        ("heka-identity-platform", "Identity"),
        # Plain SDK channels.
        ("hiero-sdk-python", "SDKs"),
        ("hiero-sdk-cpp", "SDKs"),
        ("hiero-enterprise-java", "SDKs"),
        ("hiero-sdk-v3-playground", "SDKs"),
        # Governance / Core / Tooling sentinels.
        ("hiero-maintainers", "Governance"),
        ("hiero-hips", "Governance"),
        ("hiero-community-management", "Governance"),
        ("hiero-consensus-node", "Core"),
        ("hiero-mirror-node", "Core"),
        ("solo", "Tooling"),
        ("hiero-solo-action", "Tooling"),
        # Community fallback.
        ("hiero-general", "Community"),
        ("hiero-website", "Community"),
        ("hiero-gfi", "Community"),
        ("hedera-dev-announcements-xp", "Community"),
        ("some-future-channel", "Community"),
    ],
)
def test_categorize_channel_maps_known_channels(channel: str, expected: str) -> None:
    assert runner._categorize_channel(channel) == expected


def test_load_channels_df_raises_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HIERO_DISCORD_CHANNELS_CSV", str(tmp_path / "does-not-exist.csv"))

    with pytest.raises(FileNotFoundError, match="HIERO_DISCORD_CHANNELS_CSV"):
        runner.load_channels_df()


def test_load_monthly_df_parses_and_sorts(monthly_csv: Path) -> None:
    df = runner.load_monthly_df()

    # Datetime conversion lets the chart use date-aware locators.
    assert pd.api.types.is_datetime64_any_dtype(df["month"])
    # Loader must sort ascending so the line chart reads chronologically.
    assert df["month"].is_monotonic_increasing
    assert df["month"].iloc[0] == pd.Timestamp("2024-09-01")
    assert df["month"].iloc[-1] == pd.Timestamp("2026-02-01")


def test_load_monthly_df_raises_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HIERO_DISCORD_MONTHLY_CSV", str(tmp_path / "missing.csv"))

    with pytest.raises(FileNotFoundError, match="HIERO_DISCORD_MONTHLY_CSV"):
        runner.load_monthly_df()


def test_resolve_path_falls_back_to_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without an env override the loader uses the bundled default path."""
    monkeypatch.delenv("HIERO_DISCORD_CHANNELS_CSV", raising=False)
    default = tmp_path / "default.csv"

    resolved = runner._resolve_path("HIERO_DISCORD_CHANNELS_CSV", default)

    assert resolved == default


# --------------------------------------------------------------------------- #
# Chart-writer smoke tests
# --------------------------------------------------------------------------- #

def test_plot_recent_activity_30d_writes_png(tmp_path: Path, channels_csv: Path) -> None:
    output = tmp_path / "recent.png"
    runner.plot_recent_activity_30d(runner.load_channels_df(), output)

    assert output.exists() and output.stat().st_size > 0


def test_plot_recent_activity_30d_filters_zero_d30_and_caps_top_n(channels_csv: Path) -> None:
    """The chart must drop zero-message channels and respect ``top_n``."""
    with patch.object(runner, "plot_bar") as mock_plot_bar:
        runner.plot_recent_activity_30d(runner.load_channels_df(), Path("/unused.png"), top_n=2)

    assert mock_plot_bar.call_count == 1
    passed_df = mock_plot_bar.call_args.kwargs.get("df") or mock_plot_bar.call_args.args[0]

    # Only top_n rows, sorted descending, no zero-d30 channels.
    assert len(passed_df) == 2
    counts = passed_df["messages (last 30d)"].tolist()
    assert counts == sorted(counts, reverse=True)
    assert "#hiero-sdk-java" not in passed_df["channel_label"].tolist()
    assert "#hiero-hips" not in passed_df["channel_label"].tolist()


def test_plot_category_breakdown_writes_png(tmp_path: Path, channels_csv: Path) -> None:
    output = tmp_path / "categories.png"
    runner.plot_category_breakdown(runner.load_channels_df(), output)

    assert output.exists() and output.stat().st_size > 0


def test_plot_monthly_traffic_writes_png(tmp_path: Path, monthly_csv: Path) -> None:
    output = tmp_path / "monthly.png"
    runner.plot_monthly_traffic(runner.load_monthly_df(), output)

    assert output.exists() and output.stat().st_size > 0


# --------------------------------------------------------------------------- #
# End-to-end wiring
# --------------------------------------------------------------------------- #

def test_main_writes_three_charts(
    tmp_path: Path,
    channels_csv: Path,
    monthly_csv: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``main()`` must produce all three expected PNGs in the org charts dir."""
    charts_dir = tmp_path / "charts"
    charts_dir.mkdir()
    monkeypatch.setattr(
        runner, "ensure_org_dirs", lambda _org: (tmp_path / "data", charts_dir)
    )

    runner.main()

    expected = {
        "hiero_discord_monthly_traffic.png",
        "hiero_discord_recent_activity_30d.png",
        "hiero_discord_channel_categories.png",
    }
    actual = {p.name for p in charts_dir.glob("*.png")}
    assert expected == actual
    for png in charts_dir.glob("*.png"):
        assert png.stat().st_size > 0
