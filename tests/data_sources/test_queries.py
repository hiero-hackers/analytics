"""Tests for GraphQL query-document loading."""

from __future__ import annotations

import pytest

import hiero_analytics.data_sources.queries as queries


def test_load_query_reads_file_and_caches(monkeypatch, tmp_path):
    """Queries should be read from disk and cached on subsequent calls."""
    queries_dir = tmp_path / "queries"
    queries_dir.mkdir(parents=True)
    (queries_dir / "test_query.graphql").write_text("{ viewer { login } }", encoding="utf-8")

    monkeypatch.setattr(queries, "_QUERIES_DIR", queries_dir)
    queries._query_cache.clear()

    result = queries.load_query("test_query")

    assert result == "{ viewer { login } }"
    assert "test_query" in queries._query_cache

    # second call should return from cache without re-reading
    result_cached = queries.load_query("test_query")
    assert result_cached == result

    queries._query_cache.clear()


def test_load_query_appends_referenced_fragments(monkeypatch, tmp_path):
    """A query spreading a fragment has that fragment's definition appended."""
    queries_dir = tmp_path / "queries"
    (queries_dir / "fragments").mkdir(parents=True)
    (queries_dir / "q.graphql").write_text("query { repository { ...Foo } }", encoding="utf-8")
    (queries_dir / "fragments" / "Foo.graphql").write_text("fragment Foo on Repository { name }", encoding="utf-8")

    monkeypatch.setattr(queries, "_QUERIES_DIR", queries_dir)
    queries._query_cache.clear()

    result = queries.load_query("q")

    assert "...Foo" in result  # the spread stays in the query
    assert "fragment Foo on Repository { name }" in result  # definition appended
    queries._query_cache.clear()


def test_load_query_raises_on_missing_file(monkeypatch, tmp_path):
    """A non-existent query name should raise FileNotFoundError."""
    monkeypatch.setattr(queries, "_QUERIES_DIR", tmp_path)
    queries._query_cache.clear()

    with pytest.raises(FileNotFoundError):
        queries.load_query("nonexistent_query")

    queries._query_cache.clear()
