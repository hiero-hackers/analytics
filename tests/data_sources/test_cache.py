import json
from pathlib import Path

import pytest

import hiero_analytics.data_sources.cache as cache


@pytest.fixture
def temp_cache_dir(tmp_path, monkeypatch):
    """
    Redirect CACHE_DIR to a temporary directory so tests
    do not write to the real filesystem cache.
    """
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    return tmp_path


def test_cache_path_sanitization(temp_cache_dir):
    key = "repos/hiero-ledger:issues"
    path = cache._path(key)

    assert path.name == "repos_hiero-ledger_issues.json"


def test_load_cache_miss_returns_none(temp_cache_dir):
    result = cache.load_cache("nonexistent-key")
    assert result is None


def test_save_and_load_cache_roundtrip(temp_cache_dir):
    key = "test-key"
    data = {"hello": "world", "value": 42}

    cache.save_cache(key, data)
    loaded = cache.load_cache(key)

    assert loaded == data


def test_cache_file_created(temp_cache_dir):
    key = "file-created-test"
    data = {"a": 1}

    cache.save_cache(key, data)

    path = cache._path(key)
    assert path.exists()

    with open(path) as f:
        contents = json.load(f)

    assert contents == data


def test_cache_overwrite(temp_cache_dir):
    key = "overwrite-test"

    cache.save_cache(key, {"v": 1})
    cache.save_cache(key, {"v": 2})

    loaded = cache.load_cache(key)

    assert loaded == {"v": 2}