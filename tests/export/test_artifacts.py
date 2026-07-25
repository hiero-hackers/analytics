"""Tests for reading generated artifacts back for rendering."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from hiero_analytics.export.artifacts import csv_data_uri, generated_at, load_csv, png_data_uri, stamp_freshness


def test_generated_at_reads_sidecar_and_tolerates_absence(tmp_path: Path):
    """The sidecar timestamp is read when present; absent or malformed means None."""
    path = tmp_path / "table.csv"
    assert generated_at(path) is None

    (tmp_path / "table.csv.meta.json").write_text('{"generated_at": "2026-07-24T01:02:03+00:00"}', encoding="utf-8")
    assert generated_at(path) == datetime(2026, 7, 24, 1, 2, 3, tzinfo=UTC)

    (tmp_path / "table.csv.meta.json").write_text("not json", encoding="utf-8")
    assert generated_at(path) is None


def test_stamp_freshness_marks_stale_data(tmp_path: Path):
    """A section is stamped from its source's sidecar and flagged when overdue."""
    path = tmp_path / "table.csv"
    fresh, stale = {}, {}

    stamp_freshness(fresh, path)
    assert fresh == {}  # no sidecar, no stamp

    recent = datetime.now(UTC) - timedelta(hours=1)
    (tmp_path / "table.csv.meta.json").write_text(f'{{"generated_at": "{recent.isoformat()}"}}', encoding="utf-8")
    stamp_freshness(fresh, path)
    assert fresh["stale"] is False and fresh["data_as_of"].endswith("UTC")

    old = datetime.now(UTC) - timedelta(days=5)
    (tmp_path / "table.csv.meta.json").write_text(f'{{"generated_at": "{old.isoformat()}"}}', encoding="utf-8")
    stamp_freshness(stale, path)
    assert stale["stale"] is True


def test_load_csv_tolerates_missing_file(tmp_path: Path):
    """A missing produced CSV reads as an empty frame, not an error."""
    assert load_csv(tmp_path / "absent.csv").empty


def test_data_uris_are_self_contained(tmp_path: Path):
    """Payloads inline as base64 data: URIs so the page needs no network."""
    assert csv_data_uri("a,b\n1,2\n").startswith("data:text/csv;base64,")
    assert png_data_uri(tmp_path / "absent.png") is None
    (tmp_path / "chart.png").write_bytes(b"\x89PNG")
    assert png_data_uri(tmp_path / "chart.png").startswith("data:image/png;base64,")
