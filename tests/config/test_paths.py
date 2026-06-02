"""Tests for path configuration and directory helpers."""

from __future__ import annotations

import pytest

import hiero_analytics.config.paths as paths

# -- ensure_output_dirs -------------------------------------------------------


def test_ensure_output_dirs_creates_all_directories(monkeypatch, tmp_path):
    """All seven output directories should be created on first call."""
    dirs = {
        "OUTPUTS_DIR": tmp_path / "outputs",
        "DATA_DIR": tmp_path / "outputs" / "data",
        "CHARTS_DIR": tmp_path / "outputs" / "charts",
        "REPO_DATA_DIR": tmp_path / "outputs" / "data" / "repo",
        "ORG_DATA_DIR": tmp_path / "outputs" / "data" / "org",
        "REPO_CHARTS_DIR": tmp_path / "outputs" / "charts" / "repo",
        "ORG_CHARTS_DIR": tmp_path / "outputs" / "charts" / "org",
    }
    for attr, path in dirs.items():
        monkeypatch.setattr(paths, attr, path)

    paths.ensure_output_dirs()

    for path in dirs.values():
        assert path.is_dir()


def test_ensure_output_dirs_is_idempotent(monkeypatch, tmp_path):
    """Calling ensure_output_dirs twice should not raise."""
    dirs = {
        "OUTPUTS_DIR": tmp_path / "outputs",
        "DATA_DIR": tmp_path / "outputs" / "data",
        "CHARTS_DIR": tmp_path / "outputs" / "charts",
        "REPO_DATA_DIR": tmp_path / "outputs" / "data" / "repo",
        "ORG_DATA_DIR": tmp_path / "outputs" / "data" / "org",
        "REPO_CHARTS_DIR": tmp_path / "outputs" / "charts" / "repo",
        "ORG_CHARTS_DIR": tmp_path / "outputs" / "charts" / "org",
    }
    for attr, path in dirs.items():
        monkeypatch.setattr(paths, attr, path)

    paths.ensure_output_dirs()
    paths.ensure_output_dirs()  # second call must not raise


# -- ensure_org_dirs ----------------------------------------------------------


def test_ensure_org_dirs_creates_directories(monkeypatch, tmp_path):
    """Org-specific data and chart directories should be created."""
    monkeypatch.setattr(paths, "ORG_DATA_DIR", tmp_path / "data" / "org")
    monkeypatch.setattr(paths, "ORG_CHARTS_DIR", tmp_path / "charts" / "org")

    data_dir, charts_dir = paths.ensure_org_dirs("test-org")

    assert data_dir.is_dir()
    assert charts_dir.is_dir()
    assert data_dir.name == "test-org"
    assert charts_dir.name == "test-org"


def test_ensure_org_dirs_sanitizes_slash(monkeypatch, tmp_path):
    """Slashes in org names should be replaced with underscores."""
    monkeypatch.setattr(paths, "ORG_DATA_DIR", tmp_path / "data" / "org")
    monkeypatch.setattr(paths, "ORG_CHARTS_DIR", tmp_path / "charts" / "org")

    data_dir, charts_dir = paths.ensure_org_dirs("org/sub")

    assert data_dir.name == "org_sub"
    assert charts_dir.name == "org_sub"
    assert data_dir.is_dir()
    assert charts_dir.is_dir()


# -- ensure_repo_dirs ---------------------------------------------------------


def test_ensure_repo_dirs_creates_directories(monkeypatch, tmp_path):
    """Repo-specific data and chart directories should be created."""
    monkeypatch.setattr(paths, "REPO_DATA_DIR", tmp_path / "data" / "repo")
    monkeypatch.setattr(paths, "REPO_CHARTS_DIR", tmp_path / "charts" / "repo")

    data_dir, charts_dir = paths.ensure_repo_dirs("my-repo")

    assert data_dir.is_dir()
    assert charts_dir.is_dir()
    assert data_dir.name == "my-repo"
    assert charts_dir.name == "my-repo"


def test_ensure_repo_dirs_sanitizes_slash(monkeypatch, tmp_path):
    """Slashes in repo names should be replaced with underscores."""
    monkeypatch.setattr(paths, "REPO_DATA_DIR", tmp_path / "data" / "repo")
    monkeypatch.setattr(paths, "REPO_CHARTS_DIR", tmp_path / "charts" / "repo")

    data_dir, charts_dir = paths.ensure_repo_dirs("owner/repo")

    assert data_dir.name == "owner_repo"
    assert charts_dir.name == "owner_repo"
    assert data_dir.is_dir()
    assert charts_dir.is_dir()


# -- load_query ---------------------------------------------------------------


def test_load_query_reads_file_and_caches(monkeypatch, tmp_path):
    """Queries should be read from disk and cached on subsequent calls."""
    queries_dir = tmp_path / "data_sources" / "queries"
    queries_dir.mkdir(parents=True)
    query_file = queries_dir / "test_query.graphql"
    query_file.write_text("{ viewer { login } }", encoding="utf-8")

    monkeypatch.setattr(paths, "SRC", tmp_path)
    paths._query_cache.clear()

    result = paths.load_query("test_query")

    assert result == "{ viewer { login } }"
    assert "test_query" in paths._query_cache

    # second call should return from cache without re-reading
    result_cached = paths.load_query("test_query")
    assert result_cached == result

    paths._query_cache.clear()


def test_load_query_raises_on_missing_file(monkeypatch, tmp_path):
    """A non-existent query name should raise FileNotFoundError."""
    monkeypatch.setattr(paths, "SRC", tmp_path)
    paths._query_cache.clear()

    with pytest.raises(FileNotFoundError):
        paths.load_query("nonexistent_query")

    paths._query_cache.clear()
