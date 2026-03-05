from hiero_analytics.data_sources.pagination import (
    paginate_page_number,
    paginate_cursor,
)


def test_paginate_page_number_multiple_pages():

    pages = {
        1: [1, 2, 3],
        2: [4, 5],
        3: [],
    }

    def fetch_page(page):
        return pages[page]

    results = paginate_page_number(fetch_page, page_size=3)

    assert results == [1, 2, 3, 4, 5]


def test_paginate_page_number_empty():

    def fetch_page(page):
        return []

    results = paginate_page_number(fetch_page)

    assert results == []


def test_paginate_page_number_single_page():

    def fetch_page(page):
        if page == 1:
            return [1, 2]
        return []

    results = paginate_page_number(fetch_page, page_size=100)

    assert results == [1, 2]


def test_paginate_cursor_multiple_pages():

    pages = {
        None: ([1, 2], "cursor1", True),
        "cursor1": ([3, 4], "cursor2", True),
        "cursor2": ([5], None, False),
    }

    def fetch_page(cursor):
        return pages[cursor]

    results = paginate_cursor(fetch_page)

    assert results == [1, 2, 3, 4, 5]


def test_paginate_cursor_single_page():

    def fetch_page(cursor):
        return ([1, 2, 3], None, False)

    results = paginate_cursor(fetch_page)

    assert results == [1, 2, 3]


def test_paginate_cursor_empty():

    def fetch_page(cursor):
        return ([], None, False)

    results = paginate_cursor(fetch_page)

    assert results == []