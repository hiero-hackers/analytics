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
    """max_pages stops a cursor that keeps advancing, after that many pages."""

    def fetch(cursor, _page_size):
        page_no = 0 if cursor is None else int(cursor)
        return ([page_no], str(page_no + 1), True)

    results = pagination.paginate_cursor(
        fetch,
        max_pages=2,
    )

    assert results == [0, 1]


def test_paginate_cursor_handles_empty_items():
    """Test that an empty items page returns an empty list."""
    calls = {None: ([], None, False)}

    def fetch(cursor, _page_size):
        return calls[cursor]

    results = pagination.paginate_cursor(fetch)

    assert results == []


# ---------------------------------------------------------
# stalled cursors
# ---------------------------------------------------------


@pytest.mark.parametrize("next_cursor", [None, "", 5])
def test_paginate_cursor_raises_when_the_cursor_does_not_advance(next_cursor):
    """A claimed next page with no usable cursor retries once and raises, instead of running to max_pages."""
    calls = []

    def fetch(cursor, _page_size):
        calls.append(cursor)
        return ([1], next_cursor, True)

    with pytest.raises(pagination.CursorStalledError, match="did not advance"):
        pagination.paginate_cursor(fetch, max_pages=50)

    assert calls == [None, None]


def test_paginate_cursor_raises_when_a_later_page_repeats_its_cursor():
    """A cursor that advances once and then repeats raises, instead of appending that page forever."""
    calls = []

    def fetch(cursor, _page_size):
        calls.append(cursor)
        if cursor is None:
            return ([1], "A", True)
        return ([2], "A", True)

    with pytest.raises(pagination.CursorStalledError, match=r"cursor='A'"):
        pagination.paginate_cursor(fetch)

    assert calls == [None, "A", "A"]


def test_paginate_cursor_retries_a_repeated_cursor_without_keeping_duplicate_items(caplog):
    """One repeated cursor is fetched again; the stalled response's items are not appended."""
    attempts = {"A": 0}

    def fetch(cursor, _page_size):
        if cursor is None:
            return ([1, 2], "A", True)
        attempts["A"] += 1
        if attempts["A"] == 1:
            return ([1, 2], "A", True)
        return ([3], None, False)

    with caplog.at_level(logging.WARNING, logger=pagination.logger.name):
        results = pagination.paginate_cursor(fetch)

    assert results == [1, 2, 3]
    assert attempts["A"] == 2
    assert sum("retrying the same page" in record.getMessage() for record in caplog.records) == 1


def test_paginate_cursor_retries_a_missing_cursor_then_continues():
    """A first page that claims a successor but omits the cursor succeeds when the retry supplies one."""
    calls = []

    def fetch(cursor, _page_size):
        calls.append(cursor)
        if cursor is None and len(calls) == 1:
            return ([1], None, True)
        if cursor is None:
            return ([1], "A", True)
        return ([2], None, False)

    assert pagination.paginate_cursor(fetch) == [1, 2]
    assert calls == [None, None, "A"]


def test_paginate_cursor_allows_one_stall_on_each_page():
    """The retry budget is per stalled page, so a later hiccup also self-heals."""
    seen: dict[str | None, int] = {}

    def fetch(cursor, _page_size):
        seen[cursor] = seen.get(cursor, 0) + 1
        if cursor is None:
            if seen[None] == 1:
                return ([1], None, True)
            return ([1], "A", True)
        if seen["A"] == 1:
            return ([2], "A", True)
        return ([2], None, False)

    assert pagination.paginate_cursor(fetch) == [1, 2]
    assert seen == {None: 2, "A": 2}


def test_paginate_cursor_retries_a_stall_at_the_same_page_size():
    """A stall is not a server error: the retry asks for the same page size."""
    calls = []

    def fetch(cursor, page_size):
        calls.append((cursor, page_size))
        if len(calls) == 1:
            return ([1], None, True)
        if cursor is None:
            return ([1], "A", True)
        return ([2], None, False)

    assert pagination.paginate_cursor(fetch, page_size=80, min_page_size=10) == [1, 2]
    assert calls == [(None, 80), (None, 80), ("A", 80)]


def test_paginate_cursor_start_cursor_must_advance():
    """start_cursor is the cursor actually sent, so echoing it is a stall, not the first page."""
    calls = []

    def fetch(cursor, _page_size):
        calls.append(cursor)
        if len(calls) == 1:
            return ([1], "seed", True)
        if len(calls) == 2:
            return ([2], "next", True)
        return ([3], None, False)

    results = pagination.paginate_cursor(fetch, start_cursor="seed")

    assert calls == ["seed", "seed", "next"]
    assert results == [2, 3]


def test_paginate_cursor_stall_does_not_count_as_a_clean_page():
    """A discarded stall is not one of the successes that grow the page size back."""
    calls = []

    def fetch(cursor, page_size):
        calls.append((cursor, page_size))
        if len(calls) == 1:
            raise GitHubServerError("502")
        if cursor is None and len(calls) == 2:
            return ([1], None, True)
        if cursor is None:
            return ([1], "A", True)
        nxt = {"A": "B", "B": "C", "C": None}[cursor]
        return ([1], nxt, nxt is not None)

    pagination.paginate_cursor(fetch, page_size=100, min_page_size=10)

    # The 502 shrinks to 50. The stall is retried at 50 and does not count, so
    # recovery to 100 waits for three accepted pages after that retry.
    assert [size for _cursor, size in calls] == [100, 50, 50, 50, 50, 100]


def test_paginate_cursor_accepts_a_last_page_whose_cursor_does_not_advance():
    """A repeated cursor ends the fetch when the API says there is no next page."""

    def fetch(cursor, _page_size):
        if cursor is None:
            return ([1], "A", True)
        return ([2], "A", False)

    assert pagination.paginate_cursor(fetch) == [1, 2]


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


def test_paginate_cursor_catches_a_cursor_that_cycles_back():
    """A cursor already sent earlier (A, B, A) stalls like an immediate repeat: retried once, then raised."""
    pages = {None: ([1], "A", True), "A": ([2], "B", True), "B": ([3], "A", True)}
    calls = []

    def fetch(cursor, _page_size):
        calls.append(cursor)
        return pages[cursor]

    with pytest.raises(pagination.CursorStalledError):
        pagination.paginate_cursor(fetch)

    assert calls == [None, "A", "B", "B"]


def test_paginate_cursor_hard_page_cap_raises_instead_of_truncating():
    """Past hard_max_pages the paginator raises; it never returns the pages collected so far."""

    def fetch(cursor, _page_size):
        index = int(cursor or 0)
        return ([index], str(index + 1), True)

    with pytest.raises(pagination.PaginationLimitError, match="exceeded 3 pages"):
        pagination.paginate_cursor(fetch, hard_max_pages=3)


def test_paginate_cursor_soft_max_pages_still_truncates_below_the_hard_cap():
    """max_pages keeps its documented meaning: stop and return what was collected."""

    def fetch(cursor, _page_size):
        index = int(cursor or 0)
        return ([index], str(index + 1), True)

    assert pagination.paginate_cursor(fetch, max_pages=2, hard_max_pages=10) == [0, 1]


def test_page_size_policy_names_what_it_shrinks(caplog):
    """The batched engine reuses the policy for its round width; the log line says which quantity moved."""
    policy = pagination.PageSizePolicy(5, 1, label="GraphQL batch width")

    with caplog.at_level(logging.WARNING, logger=pagination.logger.name):
        assert policy.shrink("GraphQL resource limits exceeded")

    assert policy.current == 2
    assert any(
        record.getMessage() == "GraphQL resource limits exceeded; reducing GraphQL batch width from 5 to 2 and retrying"
        for record in caplog.records
    )
