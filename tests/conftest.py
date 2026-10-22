"""Shared pytest configuration for the analytics test suite."""

import pytest

import hiero_analytics.data_sources.cache as cache
from hiero_analytics.config import paths
from hiero_analytics.data_sources import dataset_store


@pytest.fixture(autouse=True)
def isolate_github_cache(monkeypatch, tmp_path):
    """Keep tests isolated from any real on-disk GitHub cache state."""
    monkeypatch.setattr(cache, "GITHUB_CACHE_DIR", tmp_path / "github")


@pytest.fixture(autouse=True)
def isolate_datasets_dir(monkeypatch, tmp_path):
    """Point the persisted-dataset directory at a sandbox for every test.

    The store now *deletes* orphaned datasets, and several tests drive
    ``run_all.main()`` end to end. Without this, one of those could reclaim a
    developer's real dataset cache — which is precisely what happened while this
    prune was being written, costing a full re-fetch to recover.

    The touch record is process-wide, so it is cleared per test too: leakage
    between tests would otherwise decide what counts as an orphan.
    """
    datasets = tmp_path / "datasets"
    datasets.mkdir()
    monkeypatch.setattr(paths, "DATASETS_DIR", datasets)
    dataset_store.forget_touched_datasets()
    yield
    dataset_store.forget_touched_datasets()


@pytest.fixture(autouse=True)
def isolate_org_roster(monkeypatch):
    """Keep a developer's ``.env`` from changing which orgs a test run renders.

    ``config/__init__`` loads ``.env`` into the environment, and a local file
    commonly sets ``GITHUB_EXTRA_ORGS``. The org registry reads these variables
    at call time, so a test that drives the full run would otherwise render
    whatever that file says rather than the registry the test arranged.
    """
    for name in ("GITHUB_EXTRA_ORGS", "HIERO_ANALYTICS_TRIAL_ORGS", "GOVERNANCE_CONFIG_URL", "HIP_PROPOSALS_REPO"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def skip_org_preflight(monkeypatch):
    """Never call GitHub to check an org login from a test.

    ``run_all`` asks GitHub for each org's canonical spelling before fetching;
    with a token in ``.env`` that would be a real network call. The lookup is
    faked to echo the login back (every org "exists, spelt as given") and the
    shared client is never built for it; tests of the check override the fake.
    """
    from hiero_analytics.pipelines import run_all

    monkeypatch.setattr(run_all, "shared_client", lambda: None)
    monkeypatch.setattr(run_all, "fetch_org_login", lambda _client, org: org)
