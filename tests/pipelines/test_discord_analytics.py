"""Regression tests for the Hiero Discord analytics runner."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import hiero_analytics.pipelines.discord_analytics as runner

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

CHANNELS_CSV_TEXT = (
    "channel,last_message,d30,d90,d365,total\n"
    "hiero-sdk-python,2026-05-11,87,125,322,483\n"
    "hiero-general,2026-05-10,95,124,160,200\n"
    "hiero-sdk-cpp,2026-05-10,27,29,55,56\n"
    "hiero-website,2026-04-28,15,56,155,155\n"
    "hiero-sdk-java,2026-02-02,0,0,4,8\n"  # zero d30 stays in the CSV
    "hiero-hips,2026-02-09,0,0,4,9\n"  # zero d30 stays in the CSV
)

# Intentionally unsorted to verify load_monthly_df sorts ascending.
MONTHLY_CSV_TEXT = "month,messages\n2026-01,258\n2025-12,31\n2026-02,230\n2024-09,13\n"


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
    """Test that load_channels_df reads the CSV and derives label and category columns."""
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
    """Test that _categorize_channel returns the expected category for each channel."""
    assert runner._categorize_channel(channel) == expected


def test_load_channels_df_raises_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that load_channels_df raises FileNotFoundError when the CSV is missing."""
    monkeypatch.setenv("HIERO_DISCORD_CHANNELS_CSV", str(tmp_path / "does-not-exist.csv"))

    with pytest.raises(FileNotFoundError, match="HIERO_DISCORD_CHANNELS_CSV"):
        runner.load_channels_df()


def test_load_monthly_df_parses_and_sorts(monthly_csv: Path) -> None:
    """Test that load_monthly_df parses datetimes and returns rows sorted ascending."""
    df = runner.load_monthly_df()

    # Datetime conversion gives the exported series a date dtype.
    assert pd.api.types.is_datetime64_any_dtype(df["month"])
    # Loader must sort ascending so the series reads chronologically.
    assert df["month"].is_monotonic_increasing
    assert df["month"].iloc[0] == pd.Timestamp("2024-09-01")
    assert df["month"].iloc[-1] == pd.Timestamp("2026-02-01")


def test_load_monthly_df_raises_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that load_monthly_df raises FileNotFoundError when the CSV is missing."""
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
# Table builders
# --------------------------------------------------------------------------- #


def test_category_breakdown_ranks_categories_and_splits_recent_from_earlier() -> None:
    """The exported CSV is this one frame: busiest category first, earlier = total - last 90 days."""
    channels = pd.DataFrame(
        {
            "category": ["Dev", "General", "Dev", "Events"],
            "total": [100, 300, 50, 10],
            "d90": [40, 20, 10, 10],
        }
    )
    categories = runner.category_breakdown(channels)
    assert categories.to_dict("records") == [
        {"category": "General", "total": 300, "last_90d": 20, "earlier": 280},
        {"category": "Dev", "total": 150, "last_90d": 50, "earlier": 100},
        {"category": "Events", "total": 10, "last_90d": 10, "earlier": 0},
    ]


# --------------------------------------------------------------------------- #
# End-to-end wiring
# --------------------------------------------------------------------------- #


def test_main_writes_three_csvs_with_meta(
    tmp_path: Path,
    channels_csv: Path,
    monthly_csv: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``main()`` writes the three CSVs (unfiltered recent activity) plus their meta sidecars."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(runner, "ensure_org_dirs", lambda _org: data_dir)

    runner.main()

    assert {p.name for p in data_dir.glob("*.csv")} == {
        "hiero_discord_monthly_traffic.csv",
        "hiero_discord_recent_activity_30d.csv",
        "hiero_discord_channel_categories.csv",
    }
    recent = pd.read_csv(data_dir / "hiero_discord_recent_activity_30d.csv")
    assert list(recent.columns) == ["channel_label", "d30"]
    assert len(recent) == 6  # zero-d30 channels are kept
    for csv in data_dir.glob("*.csv"):
        assert Path(f"{csv}.meta.json").exists()


def test_main_exports_chart_data_at_manual_snapshot_date(channels_csv, monthly_csv, tmp_path, monkeypatch):
    """Rerendering a manual archive must not extend its calendar series to today."""
    import json

    from hiero_analytics.dashboard_spec.interactive import DISCORD_SOURCES
    from hiero_analytics.export.chart_data import chart_document

    data_dir = tmp_path / "data"
    monkeypatch.setattr(runner, "ensure_org_dirs", lambda _org: data_dir)
    runner.main()
    documents = {}
    for name, source in DISCORD_SOURCES.items():
        path = data_dir / source["file"]
        stamp = json.loads(Path(f"{path}.meta.json").read_text())["generated_at"]
        documents[name] = chart_document(source, path, "hiero-ledger", stamp)
        assert stamp.startswith("2026-05-12")
    assert documents["hiero_discord_monthly_traffic"]["rows"][-1]["bucket"] == "2026-05"
    categories = documents["hiero_discord_channel_categories"]["rows"]
    assert sum(row["earlier"] + row["last_90d"] for row in categories) == 911
    assert len(documents["hiero_discord_recent_activity_30d"]["rows"]) == 6


# --------------------------------------------------------------------------- #
# Invariant Validation tests
# --------------------------------------------------------------------------- #


def test_load_channels_df_valid_invariants(channels_csv: Path) -> None:
    """Test that load_channels_df succeeds when d30 <= d90 <= d365 <= total."""
    df = runner.load_channels_df()
    assert len(df) == 6


def test_load_channels_df_violates_invariant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that load_channels_df raises ValueError when d30 <= d90 <= d365 <= total is violated."""
    invalid_csv = tmp_path / "invalid_channels.csv"
    invalid_csv.write_text("channel,last_message,d30,d90,d365,total\ndev-chat,2026-05-01,100,50,200,300\n")
    monkeypatch.setenv("HIERO_DISCORD_CHANNELS_CSV", str(invalid_csv))

    with pytest.raises(ValueError, match="violates d30<=d90<=d365<=total"):
        runner.load_channels_df()
