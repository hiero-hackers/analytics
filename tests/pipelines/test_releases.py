"""Integration tests for the releases pipeline."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

import hiero_analytics.pipelines.releases as releases_pipeline
from hiero_analytics.data_sources.models import ReleaseRecord, RepositoryRecord

NOW = datetime.now(UTC)


@pytest.fixture
def synthetic_repos():
    """One repo with a release, one that has never released."""
    return [
        RepositoryRecord(full_name="org/repo1", name="repo1", owner="org"),
        RepositoryRecord(full_name="org/repo2-never-released", name="repo2-never-released", owner="org"),
    ]


@pytest.fixture
def synthetic_releases():
    """A couple of releases, only for repo1 -- one recent enough to land in every period tab."""
    return [
        ReleaseRecord(
            repo="org/repo1",
            tag_name="v1.0.0",
            name="v1.0.0",
            published_at=NOW - timedelta(days=200),
            is_prerelease=False,
        ),
        ReleaseRecord(
            repo="org/repo1",
            tag_name="v1.1.0-rc1",
            name="v1.1.0-rc1",
            published_at=NOW - timedelta(days=2),
            is_prerelease=True,
        ),
    ]


def test_main_publishes_timeline_and_staleness_tables(
    stub_pipeline_context, monkeypatch, synthetic_repos, synthetic_releases
):
    """A normal run writes both CSVs and every period-tab chart variant; the never-released repo ranks maximally stale."""
    _client, data_dir, charts_dir = stub_pipeline_context(releases_pipeline)

    monkeypatch.setattr(releases_pipeline, "fetch_org_repos_graphql", lambda _client, _org: synthetic_repos)
    monkeypatch.setattr(releases_pipeline, "fetch_org_releases_graphql", lambda _client, _org: synthetic_releases)

    releases_pipeline.main(org="org")

    timeline = pd.read_csv(data_dir / "release_timeline.csv")
    assert len(timeline) == 2
    assert set(timeline["repo"]) == {"org/repo1"}

    staleness = pd.read_csv(data_dir / "release_repo_summary.csv").set_index("repo")
    assert "org/repo1" in staleness.index
    assert "org/repo2-never-released" in staleness.index
    assert pd.isna(staleness.loc["org/repo2-never-released", "latest_release"])
    assert pd.isna(staleness.loc["org/repo2-never-released", "days_since_last_release"])
    assert not pd.isna(staleness.loc["org/repo1", "days_since_last_release"])
    assert math.isinf(staleness.loc["org/repo2-never-released", "staleness_ratio"])
    assert staleness.loc["org/repo2-never-released", "staleness_bucket"] == "never_released"

    for suffix in ("", "_7d", "_30d", "_365d"):
        chart = charts_dir / f"release_timeline{suffix}.png"
        assert chart.exists() and chart.stat().st_size > 0, f"missing {chart.name}"

    assert not (charts_dir / "release_staleness.png").exists()


def test_main_skips_cleanly_when_org_has_no_repos(stub_pipeline_context, monkeypatch):
    """No repos in the org -> no CSVs or charts written, no crash."""
    _client, data_dir, charts_dir = stub_pipeline_context(releases_pipeline)

    monkeypatch.setattr(releases_pipeline, "fetch_org_repos_graphql", lambda _client, _org: [])

    def _boom(*_args, **_kwargs):
        raise AssertionError("fetch_org_releases_graphql must not run when there are no repos")

    monkeypatch.setattr(releases_pipeline, "fetch_org_releases_graphql", _boom)

    releases_pipeline.main(org="org")

    assert list(data_dir.glob("*.csv")) == []
    assert list(charts_dir.glob("*.png")) == []


def test_main_writes_empty_but_schema_correct_tables_when_no_releases_exist(
    stub_pipeline_context, monkeypatch, synthetic_repos
):
    """Repos exist but none have released: both CSVs are written, all rank maximally stale, and no charts are plotted because there are no finite ratios."""
    _client, data_dir, charts_dir = stub_pipeline_context(releases_pipeline)

    monkeypatch.setattr(releases_pipeline, "fetch_org_repos_graphql", lambda _client, _org: synthetic_repos)
    monkeypatch.setattr(releases_pipeline, "fetch_org_releases_graphql", lambda _client, _org: [])

    releases_pipeline.main(org="org")

    timeline = pd.read_csv(data_dir / "release_timeline.csv")
    assert timeline.empty

    staleness = pd.read_csv(data_dir / "release_repo_summary.csv")
    assert len(staleness) == len(synthetic_repos)  # every repo still gets a row
    assert staleness["latest_release"].isna().all()
    assert (staleness["release_status"] == "never_released").all()
    assert staleness["staleness_ratio"].apply(math.isinf).all()  # maximally stale, not null
    assert (staleness["staleness_bucket"] == "never_released").all()

    assert list(charts_dir.glob("*.png")) == []


def test_period_tabs_only_render_when_something_falls_in_that_window(stub_pipeline_context, monkeypatch):
    """A repo with only an old release gets the wider-window variants, not Week/1 month."""
    _client, _data_dir, charts_dir = stub_pipeline_context(releases_pipeline)

    repos = [
        RepositoryRecord(
            full_name="org/old-releaser",
            name="old-releaser",
            owner="org",
        )
    ]
    records = [
        ReleaseRecord(
            repo="org/old-releaser",
            tag_name="v1",
            name="v1",
            published_at=NOW - timedelta(days=100),
            is_prerelease=False,
        )
    ]

    monkeypatch.setattr(
        releases_pipeline,
        "fetch_org_repos_graphql",
        lambda _client, _org: repos,
    )
    monkeypatch.setattr(
        releases_pipeline,
        "fetch_org_releases_graphql",
        lambda _client, _org: records,
    )

    releases_pipeline.main(org="org")

    produced = {p.name for p in charts_dir.glob("*.png")}
    assert produced == {
        "release_timeline.png",
        "release_timeline_365d.png",
    }
