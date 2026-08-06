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
