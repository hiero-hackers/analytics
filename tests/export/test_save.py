"""Tests for CSV saving and the freshness sidecar."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pandas as pd

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
