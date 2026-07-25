"""Tests for assembling generated CSVs into dashboard sections."""

from __future__ import annotations

import pandas as pd

from hiero_analytics.dashboard_spec import TABLE_FAMILIES
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
    all_specs = [spec for family in TABLE_FAMILIES.values() for spec in family.SECTION_SPECS]
    tabbed = {spec["id"]: spec for spec in all_specs if spec.get("periods")}

    assert set(tabbed) == {"profiles", "repoactivity", "understaffed", "loadshare", "repo", "teams"}
    assert all(spec["periods"] is True for spec in tabbed.values())


def test_contributor_metrics_tiles(tmp_path):
    """The Contributors tiles: counts, shares over the full list, and the 30d active share."""
    import pandas as pd

    profiles = pd.DataFrame(
        {
            "contributor": ["a", "b", "c", "d"],
            "repos_touched": [3, 1, 2, 1],
            "issues_opened": [1, 0, 0, 2],
            "prs_opened": [1, 1, 0, 0],
            "reviews_given": [0, 4, 0, 0],
        }
    )
    pd.DataFrame({"contributor": ["a"]}).to_csv(tmp_path / "contributor_activity_profiles_30d.csv", index=False)
    pd.DataFrame({"login": ["a", "b"]}).to_csv(tmp_path / "gfi_completers.csv", index=False)

    metrics = dict(dashboard._contributors_metrics({"profiles": profiles}, tmp_path))

    assert metrics["contributors"] == 4
    assert metrics["active last month %"] == "25%"
    assert metrics["multi-repo %"] == "50%"
    assert metrics["file issues %"] == "50%"
    assert metrics["open PRs %"] == "50%"
    assert metrics["give reviews %"] == "25%"
    assert metrics["completed a GFI %"] == "50%"
