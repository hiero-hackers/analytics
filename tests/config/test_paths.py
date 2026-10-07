"""Tests for path configuration and directory helpers."""

from __future__ import annotations

import hiero_analytics.config.paths as paths

# -- ensure_org_dirs ----------------------------------------------------------


def test_ensure_org_dirs_creates_the_data_directory(monkeypatch, tmp_path):
    """The org's data directory is created and returned."""
    monkeypatch.setattr(paths, "ORG_DATA_DIR", tmp_path / "data" / "org")

    data_dir = paths.ensure_org_dirs("test-org")

    assert data_dir.is_dir()
    assert data_dir == tmp_path / "data" / "org" / "test-org"


def test_ensure_org_dirs_sanitizes_slash(monkeypatch, tmp_path):
    """Slashes in org names should be replaced with underscores."""
    monkeypatch.setattr(paths, "ORG_DATA_DIR", tmp_path / "data" / "org")

    data_dir = paths.ensure_org_dirs("org/sub")

    assert data_dir.name == "org_sub"
    assert data_dir.is_dir()


def test_ensure_org_dirs_is_idempotent(monkeypatch, tmp_path):
    """Calling it twice returns the same existing directory without raising."""
    monkeypatch.setattr(paths, "ORG_DATA_DIR", tmp_path / "data" / "org")

    assert paths.ensure_org_dirs("test-org") == paths.ensure_org_dirs("test-org")


# -- ensure_repo_dirs ---------------------------------------------------------


def test_ensure_repo_dirs_creates_the_data_directory(monkeypatch, tmp_path):
    """The repo's data directory is created and returned."""
    monkeypatch.setattr(paths, "REPO_DATA_DIR", tmp_path / "data" / "repo")

    data_dir = paths.ensure_repo_dirs("my-repo")

    assert data_dir.is_dir()
    assert data_dir == tmp_path / "data" / "repo" / "my-repo"


def test_ensure_repo_dirs_sanitizes_slash(monkeypatch, tmp_path):
    """Slashes in repo names should be replaced with underscores."""
    monkeypatch.setattr(paths, "REPO_DATA_DIR", tmp_path / "data" / "repo")

    data_dir = paths.ensure_repo_dirs("owner/repo")

    assert data_dir.name == "owner_repo"
    assert data_dir.is_dir()
