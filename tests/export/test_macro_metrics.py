"""Tests for the shared metric-tile builders."""

from __future__ import annotations

import pandas as pd

from hiero_analytics.export.macro_metrics import contributors_metrics, governance_metrics, releases_metrics


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


def test_releases_metrics_scopes_percentages_to_repos_that_have_released():
    """Percentages are scoped to repos with releases, not the full repo universe.

    Most zero-release repos are docs/governance/meta, not neglected code —
    folding them into a health percentage would mostly measure "how much of
    this org is docs."
    """
    summary = pd.DataFrame(
        {
            "repo": ["a", "b", "c", "d", "e"],
            "latest_release": ["2026-07-01", "2026-01-01", None, "2026-08-01", None],
            "days_since_last_release": [39, 220, None, 8, None],
            "median_gap_days": [10, 20, None, 5, None],
            "staleness_ratio": [3.9, 11.0, None, 1.6, None],
        }
    )

    metrics = dict(releases_metrics({"release-staleness": summary}, None))

    assert metrics["repos with releases"] == "3 of 5"  # a, b, d — c and e never released
    assert metrics["released last 90d %"] == "67%"  # 2 of 3 releasing repos (a, d) within 90 days
    assert metrics[">3x their own typical gap"] == 2  # a (3.9x) and b (11.0x)


def test_releases_metrics_empty_summary_returns_no_tiles():
    """No data at all -> no tiles, not tiles with garbage values."""
    assert releases_metrics({"release-staleness": pd.DataFrame()}, None) == []


def test_releases_metrics_no_repo_has_ever_released():
    """Every repo has a row but none has released -> only the denominator tile, no percentages."""
    summary = pd.DataFrame(
        {
            "repo": ["a", "b"],
            "latest_release": [None, None],
            "days_since_last_release": [None, None],
            "median_gap_days": [None, None],
            "staleness_ratio": [None, None],
        }
    )

    metrics = releases_metrics({"release-staleness": summary}, None)

    assert metrics == [("repos with releases", "0 of 2")]
