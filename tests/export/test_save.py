"""Tests for CSV saving and the freshness sidecar."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pandas as pd

from hiero_analytics import provenance
from hiero_analytics.export.save import save_dataframe, write_output_meta


def test_save_dataframe_writes_csv_and_freshness_sidecar(tmp_path):
    """Every saved CSV gets a ``<name>.meta.json`` sidecar with a parseable stamp."""
    path = tmp_path / "sub" / "table.csv"
    before = datetime.now(UTC)

    save_dataframe(pd.DataFrame([{"a": 1}]), path)

    assert path.exists()
    meta = json.loads((tmp_path / "sub" / "table.csv.meta.json").read_text(encoding="utf-8"))
    generated = datetime.fromisoformat(meta["generated_at"])
    assert before <= generated <= datetime.now(UTC)


def test_write_output_meta_accepts_explicit_timestamp(tmp_path):
    """An explicit generated_at is stored verbatim (used by tests and backfills)."""
    stamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    target = tmp_path / "x.csv"

    write_output_meta(target, generated_at=stamp)

    meta = json.loads((tmp_path / "x.csv.meta.json").read_text(encoding="utf-8"))
    assert datetime.fromisoformat(meta["generated_at"]) == stamp


def test_sidecar_carries_revision_and_row_count(tmp_path, monkeypatch):
    """A CSV read outside the dashboard still resolves to a revision and a row count."""
    monkeypatch.setenv("GITHUB_SHA", "abc1234def")
    provenance.git_sha.cache_clear()
    path = tmp_path / "table.csv"

    save_dataframe(pd.DataFrame([{"a": 1}, {"a": 2}, {"a": 3}]), path)

    meta = json.loads((tmp_path / "table.csv.meta.json").read_text(encoding="utf-8"))
    assert meta["git_sha"] == "abc1234"
    assert meta["record_count"] == 3
    provenance.git_sha.cache_clear()


def test_sidecar_records_a_zero_row_count(tmp_path):
    """An empty table is exactly when the count matters; it must not be omitted."""
    path = tmp_path / "empty.csv"

    save_dataframe(pd.DataFrame({"a": []}), path)

    meta = json.loads((tmp_path / "empty.csv.meta.json").read_text(encoding="utf-8"))
    assert meta["record_count"] == 0


def test_csv_body_is_left_unstamped(tmp_path):
    """The CSVs are read back with pd.read_csv, so the stamp stays in the sidecar."""
    path = tmp_path / "table.csv"

    save_dataframe(pd.DataFrame([{"a": 1}]), path)

    assert path.read_text(encoding="utf-8").startswith("a\n")
    assert pd.read_csv(path).equals(pd.DataFrame([{"a": 1}]))
