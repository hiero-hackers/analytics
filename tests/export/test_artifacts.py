"""Tests for reading generated artifacts back."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from hiero_analytics.export.artifacts import load_csv


def test_load_csv_reads_a_produced_file(tmp_path: Path):
    """A produced CSV loads as its frame."""
    pd.DataFrame([{"hip": 1200, "merged_prs": 3}]).to_csv(tmp_path / "activity.csv", index=False)

    frame = load_csv(tmp_path / "activity.csv")

    assert frame.to_dict("records") == [{"hip": 1200, "merged_prs": 3}]


def test_load_csv_tolerates_missing_file(tmp_path: Path):
    """A view whose pipeline never ran reads as empty, not as an error."""
    assert load_csv(tmp_path / "absent.csv").empty
