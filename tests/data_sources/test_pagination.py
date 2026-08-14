"""Tests for the pagination data source module."""

import hiero_analytics.data_sources.pagination as pagination

# ---------------------------------------------------------
# page-number pagination
# ---------------------------------------------------------


def test_paginate_cursor_multiple_pages():
    """Test that cursor pagination accumulates items across multiple pages."""
    data = {
        None: ([1, 2], "A", True),
        "A": ([3, 4], "B", True),
        "B": ([5], None, False),
    }

    def fetch(cursor):
        return data[cursor]

    results = pagination.paginate_cursor(fetch)

    assert results == [1, 2, 3, 4, 5]


def test_paginate_cursor_single_page():
    """Test that a single-page cursor response returns all items and stops."""

    def fetch(_cursor):
        return ([1, 2], None, False)

    results = pagination.paginate_cursor(fetch)

    assert results == [1, 2]


def test_paginate_cursor_max_pages_guard():
    """Test that max_pages stops infinite cursor pagination."""

    def fetch(_cursor):
        return ([1], "next", True)

    results = pagination.paginate_cursor(
        fetch,
        max_pages=2,
    )

    assert len(results) == 2


def test_paginate_cursor_handles_empty_items():
    """Test that an empty items page returns an empty list."""
    calls = {None: ([], None, False)}

    def fetch(cursor):
        return calls[cursor]

    results = pagination.paginate_cursor(fetch)

    assert results == []


# ---------------------------------------------------------
# extract_graphql_cursor_page: defensive traversal
# ---------------------------------------------------------


def test_extract_returns_empty_when_path_traversal_hits_a_non_dict():
    """A path that runs into a non-dict value yields no nodes rather than raising."""
    data = {"data": {"repository": "unexpected-scalar"}}
    nodes, cursor, has_next = pagination.extract_graphql_cursor_page(data, ["repository", "pullRequests"])
    assert nodes == [] and cursor is None and has_next is False


def test_extract_coerces_non_list_nodes_to_empty():
    """A 'nodes' that is not a list is treated as empty, not iterated blindly."""
    data = {"data": {"repository": {"pullRequests": {"nodes": "oops", "pageInfo": {}}}}}
    nodes, _cursor, _has_next = pagination.extract_graphql_cursor_page(data, ["repository", "pullRequests"])
    assert nodes == []


def test_extract_coerces_non_dict_page_info_to_empty():
    """A malformed 'pageInfo' scalar is treated as absent rather than raising."""
    data = {"data": {"repository": {"pullRequests": {"nodes": [], "pageInfo": "oops"}}}}
    nodes, cursor, has_next = pagination.extract_graphql_cursor_page(data, ["repository", "pullRequests"])
    assert nodes == [] and cursor is None and has_next is False


def test_extract_wraps_a_bare_object_as_a_single_node():
    """A leaf object with no 'nodes' key is returned as a one-element list."""
    data = {"data": {"repository": {"owner": {"login": "alice"}}}}
    nodes, _cursor, _has_next = pagination.extract_graphql_cursor_page(data, ["repository", "owner"])
    assert nodes == [{"login": "alice"}]
