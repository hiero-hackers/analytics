"""Tests for assembling generated CSVs into dashboard sections."""

from __future__ import annotations

import pandas as pd

from hiero_analytics.dashboard_spec import SECTION_SPECS
from hiero_analytics.pipelines import dashboard


def test_load_period_variants_preserves_existing_empty_csv(tmp_path):
    """A generated zero-row period is a valid view, not a missing variant.

    Filenames derive from the spec's base ``file`` stem via ACTIVITY_PERIODS.
    """
    spec = {"file": "activity.csv", "periods": True}
    pd.DataFrame(columns=["user", "actions"]).to_csv(tmp_path / "activity_30d.csv", index=False)
    pd.DataFrame([{"user": "alice", "actions": 3}]).to_csv(tmp_path / "activity_all.csv", index=False)

    variants = dashboard._load_period_variants(spec, tmp_path)

    assert [variant["label"] for variant in variants] == ["30 days", "All time"]
    assert variants[0]["data"].empty
    assert variants[1]["data"].to_dict("records") == [{"user": "alice", "actions": 3}]


def test_load_period_variants_requires_the_flag(tmp_path):
    """Specs without the periods flag load no variants."""
    assert dashboard._load_period_variants({"file": "activity.csv"}, tmp_path) == []


def test_activity_specs_use_the_shared_period_set():
    """The tabbed activity tables opt in via the flag; filenames derive centrally."""
    tabbed = {spec["id"]: spec for spec in SECTION_SPECS if spec.get("periods")}

    assert set(tabbed) == {"profiles", "repoactivity", "understaffed", "loadshare", "repo", "teams"}
    assert all(spec["periods"] is True for spec in tabbed.values())


def test_generated_at_reads_sidecar_and_tolerates_absence(tmp_path):
    """The sidecar timestamp is read when present; absent or malformed means None."""
    from datetime import UTC, datetime

    path = tmp_path / "table.csv"
    assert dashboard._generated_at(path) is None

    (tmp_path / "table.csv.meta.json").write_text('{"generated_at": "2026-07-24T01:02:03+00:00"}', encoding="utf-8")
    assert dashboard._generated_at(path) == datetime(2026, 7, 24, 1, 2, 3, tzinfo=UTC)

    (tmp_path / "table.csv.meta.json").write_text("not json", encoding="utf-8")
    assert dashboard._generated_at(path) is None
