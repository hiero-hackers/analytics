"""Tests for GraphQL query-document loading."""

from __future__ import annotations

import re

import pytest

import hiero_analytics.data_sources.queries as queries

_PRODUCTION_QUERY_NAMES = sorted(path.stem for path in queries._QUERIES_DIR.glob("*.graphql"))
# The arguments of the connection field that carries the cursor, e.g. ``issues(first:..., after:$cursor, ...)``.
_CURSOR_EDGE_RE = re.compile(r"\w+\(([^()]*?after:\s*\$cursor[^()]*)\)")


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


@pytest.mark.parametrize("query_name", _PRODUCTION_QUERY_NAMES)
def test_paginated_queries_take_the_page_size_as_a_variable(query_name):
    """Every query paging with after:$cursor declares $pageSize and requests first:$pageSize on that edge."""
    text = queries.load_query(query_name)
    edges = _CURSOR_EDGE_RE.findall(text)
    header = text.split("{", 1)[0]

    if "after:$cursor" not in text and "after: $cursor" not in text:
        assert "$pageSize" not in header  # unpaginated queries must not demand a variable nobody sends
        return

    assert edges, f"{query_name} paginates but the cursor edge could not be located"
    assert re.search(r"\$pageSize\s*:\s*Int!", header), f"{query_name} must declare $pageSize: Int!"
    for arguments in edges:
        assert re.search(r"first:\s*\$pageSize\b", arguments), f"{query_name} cursor edge must use first:$pageSize"
        assert not re.search(r"first:\s*100\b", arguments), f"{query_name} cursor edge still hard-codes first:100"


def test_production_queries_are_discovered():
    """The glob finds the production queries, so the parametrised page-size test is not vacuous."""
    assert {"issues", "merged_pr", "repos", "pr_reviews", "contributor_activity"} <= set(_PRODUCTION_QUERY_NAMES)
