"""Tests for the pagination data source module."""

import logging

import pytest

import hiero_analytics.data_sources.pagination as pagination
from hiero_analytics.data_sources.github_client import GitHubServerError

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

    def fetch(cursor, _page_size):
        return data[cursor]

    results = pagination.paginate_cursor(fetch)

    assert results == [1, 2, 3, 4, 5]


def test_paginate_cursor_single_page():
    """Test that a single-page cursor response returns all items and stops."""

    def fetch(_cursor, _page_size):
        return ([1, 2], None, False)

    results = pagination.paginate_cursor(fetch)

    assert results == [1, 2]


def test_paginate_cursor_max_pages_guard():
    """Test that max_pages stops infinite cursor pagination."""

    def fetch(_cursor, _page_size):
        return ([1], "next", True)

    results = pagination.paginate_cursor(
        fetch,
        max_pages=2,
    )

    assert len(results) == 2


def test_paginate_cursor_handles_empty_items():
    """Test that an empty items page returns an empty list."""
    calls = {None: ([], None, False)}

    def fetch(cursor, _page_size):
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


# ---------------------------------------------------------
# adaptive page size
# ---------------------------------------------------------


def _flaky_fetch(failing_calls, pages):
    """Build a fetch_page that raises GitHubServerError on the given call numbers.

    Returns ``(fetch, calls)`` where ``calls`` records ``(cursor, page_size)`` per attempt.
    """
    calls = []

    def fetch(cursor, page_size):
        calls.append((cursor, page_size))
        if len(calls) in failing_calls:
            raise GitHubServerError("502")
        return pages[cursor]

    return fetch, calls


def test_paginate_cursor_passes_page_size_to_fetch_page():
    """The configured starting page size is handed to fetch_page on every call."""
    fetch, calls = _flaky_fetch(set(), {None: ([1], "A", True), "A": ([2], None, False)})

    pagination.paginate_cursor(fetch, page_size=40, min_page_size=5)

    assert calls == [(None, 40), ("A", 40)]


def test_paginate_cursor_halves_on_server_error_and_retries_same_cursor(caplog):
    """A server error halves the page size and retries the same cursor, logging a warning."""
    fetch, calls = _flaky_fetch({2}, {None: ([1], "A", True), "A": ([2], None, False)})

    with caplog.at_level(logging.WARNING, logger=pagination.logger.name):
        results = pagination.paginate_cursor(fetch, page_size=100, min_page_size=10)

    assert results == [1, 2]
    assert calls == [(None, 100), ("A", 100), ("A", 50)]
    assert any("100 to 50" in record.getMessage() for record in caplog.records)


def test_paginate_cursor_floors_and_reraises():
    """Repeated server errors shrink to the floor, then the error is re-raised."""
    fetch, calls = _flaky_fetch(set(range(1, 20)), {})

    with pytest.raises(GitHubServerError):
        pagination.paginate_cursor(fetch, page_size=100, min_page_size=20)

    assert calls == [(None, 100), (None, 50), (None, 25), (None, 20)]


def test_paginate_cursor_reduced_size_persists_for_later_pages():
    """After a shrink, the following pages keep requesting the reduced size."""
    pages = {None: ([1], "A", True), "A": ([2], "B", True), "B": ([3], None, False)}
    fetch, calls = _flaky_fetch({1}, pages)

    pagination.paginate_cursor(fetch, page_size=100, min_page_size=10)

    assert calls == [(None, 100), (None, 50), ("A", 50), ("B", 50)]


def test_paginate_cursor_recovers_after_three_clean_pages():
    """Three consecutive clean pages double the size back up toward the original."""
    chain = [None, "A", "B", "C", "D", "E", "F"]
    pages = {
        cursor: ([index], chain[index + 1] if index + 1 < len(chain) else None, index + 1 < len(chain))
        for index, cursor in enumerate(chain)
    }
    fetch, calls = _flaky_fetch({1}, pages)

    pagination.paginate_cursor(fetch, page_size=100, min_page_size=10)

    # The retried page and the next two are the three clean ones; the fourth page is back at 100.
    assert [size for _cursor, size in calls] == [100, 50, 50, 50, 100, 100, 100, 100]


def test_page_size_policy_starts_at_the_configured_size():
    """A fresh policy reports the starting size."""
    assert pagination.PageSizePolicy(100, 10).current == 100


def test_page_size_policy_shrink_halves_down_to_the_floor():
    """Shrinking halves with integer division, clamps to the floor, then reports False."""
    policy = pagination.PageSizePolicy(100, 30)

    assert policy.shrink() is True
    assert policy.current == 50
    assert policy.shrink() is True
    assert policy.current == 30  # 25 clamped to the floor
    assert policy.shrink() is False
    assert policy.current == 30


def test_page_size_policy_floor_is_capped_at_the_starting_size():
    """A floor larger than the starting size cannot shrink at all."""
    policy = pagination.PageSizePolicy(5, 10)

    assert policy.shrink() is False
    assert policy.current == 5


def test_page_size_policy_recovers_after_three_successes_up_to_the_start():
    """Recovery needs three consecutive successes and never exceeds the starting size."""
    policy = pagination.PageSizePolicy(100, 10)
    policy.shrink()
    policy.shrink()  # 25

    policy.record_success()
    policy.record_success()
    assert policy.current == 25
    policy.record_success()
    assert policy.current == 50
    for _ in range(3):
        policy.record_success()
    assert policy.current == 100
    for _ in range(10):
        policy.record_success()
    assert policy.current == 100


def test_page_size_policy_shrink_resets_the_clean_streak():
    """A shrink in the middle of a streak restarts the count towards recovery."""
    policy = pagination.PageSizePolicy(100, 10)
    policy.shrink()
    policy.record_success()
    policy.record_success()
    policy.shrink()  # 25, streak reset

    policy.record_success()
    policy.record_success()

    assert policy.current == 25
