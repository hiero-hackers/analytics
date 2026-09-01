"""Tests for the shared metric-tile builders."""

from __future__ import annotations

import pandas as pd

from hiero_analytics.export.macro_metrics import contributors_metrics, governance_metrics


def test_contributor_metrics_tiles(tmp_path):
    """The Contributors tiles: counts, shares over the full list, and the 30d active share."""
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

    metrics = dict(contributors_metrics({"profiles": profiles}, tmp_path))

    assert metrics["contributors"] == 4
    assert metrics["active last month %"] == "25%"
    assert metrics["multi-repo %"] == "50%"
    assert metrics["file issues %"] == "50%"
    assert metrics["open PRs %"] == "50%"
    assert metrics["give reviews %"] == "25%"
    assert metrics["completed a GFI %"] == "50%"


def test_governance_metrics_include_live_affiliation_coverage(tmp_path):
    """Known-share tiles use each role's full affiliations reference table."""
    loaded = {
        "repo": pd.DataFrame(
            {
                "user": ["alice", "bob"],
                "granted_role": ["maintainer", "committer"],
            }
        ),
        "teams": pd.DataFrame(),
        "affiliations": pd.DataFrame({"status": ["affiliated", "independent", "unknown"]}),
        "committeraffiliations": pd.DataFrame({"status": ["affiliated", "unknown", "unknown", "unknown"]}),
    }

    metrics = dict(governance_metrics(loaded, tmp_path))

    assert metrics["maintainer affiliations known"] == "67%"
    assert metrics["committer affiliations known"] == "25%"
